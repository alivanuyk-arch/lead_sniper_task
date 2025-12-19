import requests
import re
import time
import random
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
import os

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# ===================== КЭШИРОВАНИЕ И ИНДЕКСИРОВАНИЕ =====================

def load_or_create_cnews_cache(max_articles=200):
    """Загружает или создает кэш статей CNews"""
    cache_file = 'data/raw/cnews_articles.json'
    index_file = 'data/raw/cnews_index.json'
    
    # Создаем папку если нет
    os.makedirs('data/raw', exist_ok=True)
    
    # Пробуем загрузить из кэша
    if os.path.exists(cache_file) and os.path.exists(index_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Проверяем свежесть кэша (максимум 24 часа)
            cache_time = cache_data.get('timestamp', 0)
            if time.time() - cache_time < 86400:  # 24 часа
                articles = cache_data.get('articles', [])
                print(f"📂 CNews: Загружено {len(articles)} статей из кэша")
                
                # Загружаем индекс
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                
                return articles, index_data
        except:
            pass
    
    # Если кэша нет или устарел, парсим заново
    print("🔄 CNews: Создание нового кэша...")
    articles = parse_cnews_sitemap_fresh(max_articles)
    index_data = build_search_index(articles)
    
    # Сохраняем в кэш
    cache_data = {
        'timestamp': time.time(),
        'articles': articles,
        'count': len(articles)
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 CNews: Сохранено {len(articles)} статей в кэш")
    return articles, index_data

def parse_cnews_sitemap_fresh(max_articles=200):
    """Парсит свежие статьи из sitemap"""
    sitemap_urls = [
        "https://www.cnews.ru/inc/sitemap.xml",
        "https://www.cnews.ru/inc/sitemap_news.xml",
    ]
    
    all_articles = []
    
    for sitemap_url in sitemap_urls:
        try:
            print(f"📡 CNews: Загрузка sitemap...")
            response = requests.get(sitemap_url, headers=HEADERS, timeout=15)
            
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                for url in root.findall('ns:url', namespace):
                    loc = url.find('ns:loc', namespace)
                    if loc is not None:
                        article_url = loc.text.strip()
                        if '/news/' in article_url:
                            all_articles.append(article_url)
                
                print(f"  ✅ Загружено {len(all_articles)} статей")
                
                if len(all_articles) >= max_articles:
                    break
                    
            time.sleep(2)  # Пауза между sitemap
            
        except Exception as e:
            print(f"  ⚠️ Ошибка: {e}")
            continue
    
    return all_articles[:max_articles]

def build_search_index(articles, batch_size=20):
    """Создает поисковый индекс по заголовкам статей"""
    print("📇 CNews: Построение поискового индекса...")
    
    index = {}
    
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i+batch_size]
        print(f"  📄 Индексируем статьи {i+1}-{i+len(batch)}...")
        
        for url in batch:
            try:
                # Быстрый запрос только для заголовка
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code != 200:
                    continue
                
                # Парсим только заголовок
                soup = BeautifulSoup(response.content[:30000], 'html.parser')
                title_elem = soup.find('h1') or soup.find('title')
                title = title_elem.get_text(strip=True) if title_elem else ""
                
                if not title:
                    continue
                
                # Извлекаем ключевые слова из заголовка
                words = re.findall(r'\w+', title.lower())
                for word in words:
                    if len(word) > 3:  # Только значимые слова
                        if word not in index:
                            index[word] = []
                        index[word].append({
                            'url': url,
                            'title': title[:100],
                            'full_title': title
                        })
                
                time.sleep(0.5)  # Маленькая пауза
                
            except Exception:
                continue
    
    print(f"✅ CNews: Индекс построен ({len(index)} ключевых слов)")
    return index

# ===================== ОПТИМИЗИРОВАННЫЙ ПОИСК =====================

def find_articles_by_company(company_name, index, articles, max_results=10):
    """Быстрый поиск статей по компании через индекс"""
    search_variants = prepare_search_variants(company_name)
    
    found_articles = []
    
    # Ищем по ключевым словам в индексе
    for variant in search_variants:
        if variant in index:
            for article_info in index[variant]:
                if article_info['url'] not in [a['url'] for a in found_articles]:
                    found_articles.append(article_info)
                    
                    if len(found_articles) >= max_results:
                        break
        
        if len(found_articles) >= max_results:
            break
    
    # Если через индекс не нашли, ищем в URL
    if not found_articles:
        for url in articles:
            url_lower = url.lower()
            if any(variant in url_lower for variant in search_variants):
                found_articles.append({
                    'url': url,
                    'title': url.split('/')[-1].replace('-', ' ')[:50],
                    'full_title': ''
                })
                
                if len(found_articles) >= max_results:
                    break
    
    return found_articles[:max_results]

def search_patterns_in_text(text):
    """Ищет паттерны с цифрами поддержки в тексте"""
    patterns = [
        r'(?:открыл|запустил|создал|расширил|нанял|привлек).*?(?:колл.?центр|контакт.?центр|поддержк).*?(?:на|до|более|около)\s*(\d{2,})\s*(?:оператор|специалист|человек)',
        r'(\d{2,})\s*(?:оператор|специалист).*?(?:колл.?центр|поддержк)',
        r'(?:команда|штат).*?(?:из|в)\s*(\d{2,})\s*(?:человек|сотрудник)',
        r'увеличил.*?штат.*?до\s*(\d{2,})',
        r'нанял.*?(\d{2,})\s*(?:специалист|сотрудник).*?(?:поддержк|колл.?центр)',
    ]
    
    findings = []
    text_lower = text.lower()
    
    for pattern in patterns:
        matches = re.finditer(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            try:
                num = int(match.group(1))
                if num >= 10:  # Минимальный порог
                    context = text_lower[max(0, match.start()-50):match.end()+50]
                    findings.append({
                        'value': num,
                        'text': context.strip(),
                        'match': match.group(0)[:100]
                    })
                    break  # Нашли одно - достаточно
            except:
                continue
    
    return findings

def search_cnews_for_company_fast(company_name, articles, index, max_articles=15):
    """Быстрый поиск для одной компании"""
    print(f"  📰 CNews: {company_name[:30]}...")
    
    # 1. Быстрый поиск релевантных статей через индекс
    relevant_articles = find_articles_by_company(company_name, index, articles, max_results=max_articles)
    
    if not relevant_articles:
        print(f"    ➖ Не найдено статей")
        return []
    
    print(f"    📊 Найдено статей: {len(relevant_articles)}")
    
    # 2. Глубокий парсинг только релевантных статей
    findings = []
    
    for i, article_info in enumerate(relevant_articles):
        try:
            print(f"    [{i+1}/{len(relevant_articles)}] Анализ...")
            
            # Полная загрузка статьи
            response = requests.get(article_info['url'], headers=HEADERS, timeout=10)
            if response.status_code != 200:
                time.sleep(1)
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            full_text = soup.get_text()
            
            # Ищем доказательства
            article_findings = search_patterns_in_text(full_text)
            
            if article_findings:
                best_finding = max(article_findings, key=lambda x: x['value'])
                
                findings.append({
                    'type': 'CNEWS_ARTICLE',
                    'value': best_finding['value'],
                    'text': best_finding['match'],
                    'url': article_info['url'],
                    'title': article_info.get('full_title', article_info['title']),
                    'source': 'cnews',
                    'timestamp': datetime.now().isoformat(),
                    'company': company_name
                })
                
                print(f"      ✅ {best_finding['value']}+ чел.")
                
                # Большая пауза после успеха
                time.sleep(random.uniform(3, 5))
            else:
                print(f"      ➖ Не найдено")
                time.sleep(random.uniform(1.5, 2.5))
            
            # Перерыв каждые 5 статей
            if (i + 1) % 5 == 0 and i < len(relevant_articles) - 1:
                pause = random.uniform(4, 6)
                print(f"    ⏸️  Перерыв {pause:.1f}с")
                time.sleep(pause)
                
        except Exception as e:
            print(f"      ⚠️ Ошибка: {str(e)[:30]}")
            time.sleep(3)
            continue
    
    return findings

# ===================== ИНТЕГРАЦИЯ С ОСНОВНЫМ ПАЙПЛАЙНОМ =====================

# Глобальные переменные для кэша
CNEWS_CACHE = None
CNEWS_INDEX = None

def enrich_with_news(company_name, existing_findings):
    """Основная функция для интеграции в пайплайн"""
    global CNEWS_CACHE, CNEWS_INDEX
    
    print("  📰 Поиск в новостях CNews...", end=' ')
    
    try:
        # Загружаем кэш (один раз для всех компаний)
        if CNEWS_CACHE is None or CNEWS_INDEX is None:
            CNEWS_CACHE, CNEWS_INDEX = load_or_create_cnews_cache(max_articles=150)
        
        if not CNEWS_CACHE or not CNEWS_INDEX:
            print("➖ (нет данных)")
            return existing_findings
        
        # Пауза перед поиском
        time.sleep(random.uniform(1, 2))
        
        # Быстрый поиск
        cnews_findings = search_cnews_for_company_fast(
            company_name, 
            CNEWS_CACHE, 
            CNEWS_INDEX,
            max_articles=12  # Уменьшили для скорости
        )
        
        print(f"✅ {len(cnews_findings)} находок")
        
        # Объединяем результаты
        all_findings = existing_findings + cnews_findings
        
        # Пауза после поиска
        time.sleep(random.uniform(1, 3))
        
        return all_findings
        
    except Exception as e:
        print(f"⚠️ {str(e)[:30]}")
        return existing_findings

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def prepare_search_variants(company_name):
    """Подготавливает варианты для поиска"""
    name_lower = company_name.lower().strip()
    
    variants = [name_lower]
    
    # Упрощенные варианты
    words_to_remove = ['банк', 'ооо', 'ао', 'пао', 'зао', 'групп']
    simplified = name_lower
    for word in words_to_remove:
        simplified = simplified.replace(word, '').strip()
    if simplified and simplified != name_lower:
        variants.append(simplified)
    
    # Английские варианты для известных компаний
    english_names = {
        'тинькофф': 'tinkoff',
        'сбер': 'sber',
        'яндекс': 'yandex',
        'озон': 'ozon',
        'вильдберриз': 'wildberries',
        'мтс': 'mts',
        'билайн': 'beeline',
        'мегафон': 'megafon',
        'втб': 'vtb',
        'газпром': 'gazprom'
    }
    
    for ru, en in english_names.items():
        if ru in name_lower:
            variants.append(en)
    
    return [v for v in variants if v and len(v) > 2]

# ===================== ТЕСТИРОВАНИЕ =====================

def test_bulk_cnews(companies, limit=10):
    """Тестирует парсинг для нескольких компаний"""
    print(f"\n🧪 Тест CNews для {min(limit, len(companies))} компаний")
    print("=" * 60)
    
    # Загружаем кэш
    articles, index = load_or_create_cnews_cache(max_articles=150)
    
    results = {}
    
    for i, company in enumerate(companies[:limit]):
        company_name = company['name'] if isinstance(company, dict) else company
        
        print(f"\n[{i+1}/{min(limit, len(companies))}] {company_name}")
        
        findings = search_cnews_for_company_fast(company_name, articles, index, max_articles=10)
        results[company_name] = findings
        
        if findings:
            print(f"   ✅ Найдено: {len(findings)} доказательств")
            for f in findings[:2]:
                print(f"      • {f['value']} чел.: {f['text'][:60]}...")
        else:
            print(f"   ➖ Не найдено")
        
        # Пауза между компаниями
        if i < min(limit, len(companies)) - 1:
            pause = random.uniform(3, 5)
            print(f"   ⏸️  Пауза {pause:.1f}с")
            time.sleep(pause)
    
    # Статистика
    companies_with_findings = [c for c, f in results.items() if f]
    total_findings = sum(len(f) for f in results.values())
    
    print(f"\n📊 Статистика:")
    print(f"   • Компаний с находками: {len(companies_with_findings)}/{len(results)}")
    print(f"   • Всего находок: {total_findings}")
    
    return results

if __name__ == "__main__":
    # Тест с несколькими компаниями
    test_companies = ["Сбербанк", "Тинькофф", "Яндекс", "ВТБ", "МТС"]
    test_bulk_cnews(test_companies, limit=5)