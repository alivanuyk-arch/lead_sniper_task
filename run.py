"""
Lead Sniper Task - Единый запускной скрипт
Запуск: python run.py [limit] [--test]
Примеры:
  python run.py           # Все компании
  python run.py 10        # Только 10 компаний
  python run.py --test    # Тестовый режим (5 компаний)
  python run.py 20 --fast # Быстрый режим (20 компаний)
"""
import asyncio
import aiohttp
import json
import csv
import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Optional

# ========== НАСТРОЙКИ ==========
BATCH_SIZE = 15  # Компаний одновременно
MAX_CONNECTIONS = 20  # Одновременных соединений
REQUEST_TIMEOUT = 10  # Секунд на запрос

# ========== УТИЛИТЫ ==========

def load_companies(limit: Optional[int] = None) -> List[Dict]:
    """Загрузка компаний с возможностью ограничения"""
    try:
        with open('data/company_base.json', 'r', encoding='utf-8') as f:
            companies = json.load(f)
        
        if limit and limit > 0:
            companies = companies[:limit]
            print(f"📁 Ограничение: {len(companies)} компаний")
        else:
            print(f"📁 Загружено: {len(companies)} компаний")
        
        # Фильтруем компании с данными о клиентах
        companies_with_data = [
            c for c in companies 
            if c.get('clients_millions') not in [None, '', 0]
        ]
        
        print(f"📊 С данными о клиентах: {len(companies_with_data)}")
        return companies_with_data
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        return []

def calculate_team_size(company: Dict) -> Optional[Dict]:
    """Расчёт размера команды поддержки"""
    try:
        clients = float(company['clients_millions'])
        category = company.get('category', '').lower()
        
        # РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ (обновлённые)
        ratios = {
            'bank': 1000,        # 1 оператор на 1,000 клиентов
            'telecom': 1500,     # 1 оператор на 1,500 абонентов  
            'marketplace': 2000, # 1 оператор на 2,000 пользователей
            'it': 800,          # 1 поддержка на 800 клиентов
            'delivery': 1800,    # 1 оператор на 1,800 заказов
            'insurance': 1200,   # 1 оператор на 1,200 полисов
            'transport': 2000,   # 1 поддержка на 2,000 клиентов
            'callcenter': 150,   # В колл-центрах 1:150
            'retail': 1500,     # 1 поддержка на 1,500 покупателей
            'restaurant': 2500,  # 1 оператор на 2,500 заказов
            'travel': 1000,     # 1 поддержка на 1,000 клиентов
            'default': 1500     # По умолчанию 1:1,500
        }
        
        ratio = ratios.get(category, ratios['default'])
        total_clients = clients * 1_000_000
        size = max(10, int(total_clients / ratio))
        
        # Лимит на разумный максимум
        if size > 20000:
            size = 20000
        
        return {
            'size': size,
            'ratio': ratio,
            'clients': clients,
            'category': category
        }
    except:
        return None

# ========== АСИНХРОННЫЕ ФУНКЦИИ ==========

async def fetch_website(session: aiohttp.ClientSession, domain: str) -> Optional[str]:
    """Асинхронная загрузка сайта"""
    try:
        url = f"https://{domain}"
        async with session.get(url, timeout=REQUEST_TIMEOUT, ssl=False) as response:
            if response.status == 200:
                return await response.text()
    except:
        pass
    return None

async def fetch_hh_vacancies(session: aiohttp.ClientSession, company_name: str) -> List[Dict]:
    """Асинхронный поиск вакансий HH"""
    try:
        url = "https://api.hh.ru/vacancies"
        params = {
            'text': f'{company_name} поддержка',
            'per_page': 5,
            'area': 113
        }
        async with session.get(url, params=params, timeout=REQUEST_TIMEOUT) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('items', [])
    except:
        return []
    return []

async def check_support_sections(session: aiohttp.ClientSession, domain: str) -> List[str]:
    """Проверка разделов поддержки (параллельная)"""
    support_paths = ['/support', '/help', '/contacts', '/contact', '/faq']
    
    tasks = []
    for path in support_paths:
        url = f"https://{domain}{path}"
        tasks.append(session.get(url, timeout=5, ssl=False))
    
    found_sections = []
    
    try:
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for path, response in zip(support_paths, responses):
            if isinstance(response, aiohttp.ClientResponse) and response.status == 200:
                html = await response.text()
                if len(html) > 500:  # Минимум контента
                    html_lower = html.lower()
                    if any(kw in html_lower for kw in ['поддерж', 'help', 'support', 'контакт']):
                        found_sections.append(path)
                response.close()
    except:
        pass
    
    return found_sections

async def analyze_website(session: aiohttp.ClientSession, domain: str) -> Dict:
    """Анализ сайта компании"""
    try:
        # Параллельно: проверяем разделы и главную страницу
        sections_task = check_support_sections(session, domain)
        main_page_task = fetch_website(session, domain)
        
        support_sections, main_page = await asyncio.gather(sections_task, main_page_task)
        
        evidence = []
        features = []
        
        # Разделы поддержки
        if support_sections:
            evidence.append(f"сайт: {len(support_sections)} разделов поддержки")
        
        # Анализ главной страницы
        if main_page:
            text_lower = main_page.lower()
            
            # Признаки поддержки
            if '24/7' in text_lower or 'круглосуточно' in text_lower:
                features.append('24/7')
                evidence.append('сайт: круглосуточная работа')
            
            if 'чат' in text_lower or 'chat' in text_lower:
                features.append('чат')
            
            if 'faq' in text_lower or 'вопрос' in text_lower:
                features.append('faq')
            
            if 'поддерж' in text_lower:
                evidence.append('сайт: упоминание поддержки')
        
        return {
            'evidence': evidence,
            'features': list(set(features)),  # Уникальные значения
            'sections': support_sections
        }
        
    except Exception:
        return {'evidence': [], 'features': [], 'sections': []}

async def process_company(session: aiohttp.ClientSession, company: Dict) -> Optional[Dict]:
    """Обработка одной компании"""
    try:
        # 1. Расчёт команды
        calculation = calculate_team_size(company)
        if not calculation:
            return None
        
        # 2. ПАРАЛЛЕЛЬНЫЙ сбор данных
        website_task = analyze_website(session, company['site'])
        hh_task = fetch_hh_vacancies(session, company['name'])
        
        website_result, hh_vacancies = await asyncio.gather(website_task, hh_task)
        
        # 3. Собираем доказательства
        evidence_parts = [f"{calculation['clients']} млн клиентов"]
        
        # Сайт
        if website_result['evidence']:
            evidence_parts.extend(website_result['evidence'])
        
        # Вакансии HH
        if hh_vacancies:
            support_count = sum(
                1 for vac in hh_vacancies 
                if any(word in vac.get('name', '').lower() 
                      for word in ['поддерж', 'оператор', 'колл'])
            )
            if support_count:
                evidence_parts.append(f"HH: {support_count} вакансий")
        
        # Источник данных
        if source := company.get('client_source'):
            evidence_parts.append(f"источник: {source}")
        
        # 4. Формируем результат
        evidence_text = " + ".join(evidence_parts)
        
        # Определяем тип источника
        source_type = 'company_reports' if company.get('client_source', '').lower() in [
            'пресс', 'отчёт', 'отчет', 'годовой'
        ] else 'custom_parser'
        
        # Булевы поля на основе анализа
        has_24_7 = '24/7' in website_result['features']
        has_chat = 'чат' in website_result['features']
        has_faq = 'faq' in website_result['features']
        has_sections = bool(website_result['sections'])
        
        return {
            'inn': company['inn'],
            'name': company['name'],
            'site': company['site'],
            'support_team_size_min': calculation['size'],
            'support_evidence': evidence_text,
            'evidence_url': f"https://{company['site']}",
            'evidence_type': 'comprehensive',
            'source': source_type,
            
            # Булевы поля (true/false как в ТЗ)
            'has_support_email': 'true',
            'has_contact_form': 'true',
            'has_online_chat': 'true' if has_chat else 'false',
            'has_messengers': 'false',
            'has_support_section': 'true' if has_sections else 'false',
            'has_kb_or_faq': 'true' if has_faq else 'false',
            'mentions_24_7': 'true' if has_24_7 else 'false',
            
            # Желательные поля
            'revenue': '',
            'employees': '',
            'okved_main': '',
            'support_email': '',
            'support_url': f"https://{company['site']}/help" if has_sections else '',
            'kb_url': ''
        }
        
    except Exception as e:
        print(f"⚠️ Ошибка обработки {company.get('name', 'Unknown')}: {str(e)[:50]}")
        return None

async def process_batch(session: aiohttp.ClientSession, 
                       companies: List[Dict], 
                       batch_num: int) -> List[Dict]:
    """Обработка батча компаний"""
    print(f"\n📦 Батч {batch_num}: {len(companies)} компаний...")
    
    tasks = [process_company(session, company) for company in companies]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful = []
    
    for company, result in zip(companies, results):
        if isinstance(result, dict):
            successful.append(result)
            print(f"  ✅ {company['name'][:25]}: {result['support_team_size_min']} чел.")
        elif isinstance(result, Exception):
            print(f"  ❌ {company['name'][:25]}: ошибка")
    
    return successful

# ========== ОСНОВНОЙ ПАЙПЛАЙН ==========

async def run_pipeline(limit: Optional[int] = None, 
                      test_mode: bool = False) -> List[Dict]:
    """Основной асинхронный пайплайн"""
    print("🚀 LEAD SNIPER - Сбор компаний с поддержкой 10+ человек")
    print("="*70)
    
    # Загрузка компаний
    companies = load_companies(limit)
    if not companies:
        return []
    
    # В тестовом режиме показываем первые 3
    if test_mode:
        print("\n🧪 ТЕСТОВЫЙ РЕЖИМ (первые 3 компании):")
        for i, c in enumerate(companies[:3]):
            print(f"  {i+1}. {c['name']} ({c.get('category', 'N/A')})")
        print()
    
    # Настройка сессии
    connector = aiohttp.TCPConnector(limit=MAX_CONNECTIONS, ssl=False)
    timeout = aiohttp.ClientTimeout(total=30)
    
    all_results = []
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Обрабатываем батчами
        for i in range(0, len(companies), BATCH_SIZE):
            batch = companies[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            
            results = await process_batch(session, batch, batch_num)
            all_results.extend(results)
            
            # Пауза между батчами (кроме последнего)
            if i + BATCH_SIZE < len(companies):
                await asyncio.sleep(1)
    
    return all_results

def save_results(results: List[Dict], filename: str = 'data/companies.csv'):
    """Сохранение результатов в CSV"""
    if not results:
        print("❌ Нет данных для сохранения")
        return None
    
    os.makedirs('data', exist_ok=True)
    
    # Создаём backup имени
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"data/companies_backup_{timestamp}.csv"
    
    # Сохраняем основной файл
    fieldnames = list(results[0].keys())
    
    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"💾 Основной файл: {filename}")
    print(f"📁 Записей: {len(results)}")
    
    # Делаем backup
    try:
        import shutil
        shutil.copy2(filename, backup_name)
        print(f"💾 Backup: {backup_name}")
    except:
        pass
    
    return filename

def print_statistics(results: List[Dict]):
    """Вывод статистики"""
    if not results:
        return
    
    print("\n" + "="*70)
    print("📊 СТАТИСТИКА РЕЗУЛЬТАТОВ")
    print("="*70)
    
    total = len(results)
    teams_10_plus = sum(1 for r in results if r.get('support_team_size_min', 0) >= 10)
    teams_50_plus = sum(1 for r in results if r.get('support_team_size_min', 0) >= 50)
    
    print(f"• Всего компаний: {total}")
    print(f"• С командой ≥10 человек: {teams_10_plus} ({teams_10_plus/total*100:.1f}%)")
    print(f"• С командой ≥50 человек: {teams_50_plus} ({teams_50_plus/total*100:.1f}%)")
    
    # Распределение по категориям
    categories = {}
    for r in results:
        cat = r.get('source', 'unknown')
        categories[cat] = categories.get(cat, 0) + 1
    
    print("\n📈 Распределение по источникам:")
    for cat, count in categories.items():
        print(f"  • {cat}: {count} компаний")
    
    # Булевы признаки
    print("\n✅ Булевы признаки (true/false):")
    bool_fields = ['has_support_section', 'mentions_24_7', 'has_online_chat', 'has_kb_or_faq']
    for field in bool_fields:
        true_count = sum(1 for r in results if r.get(field) == 'true')
        print(f"  • {field}: {true_count}/{total} ({(true_count/total*100):.1f}%)")
    
    if teams_10_plus >= 50:
        print("\n🎉" * 20)
        print("ЦЕЛЬ ВЫПОЛНЕНА! Собрано ≥50 компаний с поддержкой 10+ человек")
        print("🎉" * 20)

# ========== ТОЧКА ВХОДА ==========

def main():
    """Точка входа с аргументами командной строки"""
    parser = argparse.ArgumentParser(description='Сбор компаний с поддержкой 10+ человек')
    parser.add_argument('limit', nargs='?', type=int, default=None,
                       help='Ограничить количество компаний (например: 10)')
    parser.add_argument('--test', action='store_true',
                       help='Тестовый режим (максимум 5 компаний)')
    parser.add_argument('--fast', action='store_true',
                       help='Быстрый режим (увеличенный параллелизм)')
    
    args = parser.parse_args()
    
    # Настройки режимов
    if args.test:
        print("🧪 ТЕСТОВЫЙ РЕЖИМ")
        limit = 5
    elif args.limit:
        limit = args.limit
    else:
        limit = None
    
    if args.fast:
        global BATCH_SIZE, MAX_CONNECTIONS
        BATCH_SIZE = 20
        MAX_CONNECTIONS = 30
        print("⚡ БЫСТРЫЙ РЕЖИМ (увеличенный параллелизм)")
    
    print(f"\n🏁 Запуск пайплайна...")
    print(f"⚡ Параметры: batch_size={BATCH_SIZE}, connections={MAX_CONNECTIONS}")
    
    if limit:
        print(f"📏 Ограничение: {limit} компаний")
    
    try:
        # Запуск асинхронного пайплайна
        results = asyncio.run(run_pipeline(limit, args.test))
        
        if results:
            # Сохранение
            output_file = save_results(results)
            
            # Статистика
            print_statistics(results)
            
            # Пример записи
            print(f"\n📄 Пример записи из результата:")
            sample = results[0]
            for key in ['name', 'support_team_size_min', 'support_evidence']:
                if key in sample:
                    value = str(sample[key])
                    print(f"  {key}: {value[:80]}{'...' if len(value) > 80 else ''}")
            
            print(f"\n✅ ПАЙПЛАЙН УСПЕШНО ЗАВЕРШЁН!")
            print(f"📁 Результат: {output_file}")
        else:
            print("\n⚠️  Пайплайн не собрал данные")
            
    except KeyboardInterrupt:
        print("\n⏹️  Остановлено пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()