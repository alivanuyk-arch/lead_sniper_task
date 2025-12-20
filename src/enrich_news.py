"""Парсинг новостей CNews с соблюдением robots.txt"""
import requests
import re
import time
import random
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import os
from urllib.parse import urlparse, urljoin

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.cnews.ru/',
    'Connection': 'keep-alive'
}

# ===================== СПИСОК ЗАПРЕЩЁННЫХ ПУТЕЙ ИЗ ROBOTS.TXT =====================
DISALLOWED_PATHS = [
    '/main/',                    # ВСЕ пути, начинающиеся с /main/
    '/news/for_blog/',          # for_blog раздел
    '/articles/for_blog/',      # статьи for_blog
    '/news/for_print/',         
    '/articles/for_print/',     
    '/articles/preview/',       
    '/news/preview/',           
    '/reviews/preview_articles/',
    '/redirect.php',            
    '/search'                   
]

ALLOWED_PATHS = [
    '/news/',
    '/articles/',
    '/analytics/',
    '/reviews/'
]

def is_url_allowed(url):
    """СТРОГОЕ соответствие robots.txt CNews"""
    try:
        parsed = urlparse(url)
        path = parsed.path  # НЕ приводим к lower()!
        
        # 1. ЯВНЫЕ запреты из robots.txt (точное соответствие началу пути)
        for disallowed in DISALLOWED_PATHS:
            if path.startswith(disallowed):
                print(f"❌ Запрещено robots.txt: {disallowed}")
                return False
        
        # 2. Разрешены ТОЛЬКО новости и статьи
        if not ('/news/' in path or '/articles/' in path or '/analytics/' in path):
            print(f"⚠️  Неизвестный раздел: {path}")
            return False
            
        # 3. Доп. проверка: не парсим динамические страницы
        if '?' in url or '#' in url or '=' in url:
            return False
            
        return True
        
    except Exception:
        return False  # При ошибке - не пропускаем


# ===================== КЭШИРОВАНИЕ И ИНДЕКСИРОВАНИЕ =====================

def load_or_create_cnews_cache(max_articles=200, max_age_hours=24):
    """Загружает или создает кэш статей CNews"""
    cache_file = 'data/raw/cnews_articles.json'
    index_file = 'data/raw/cnews_index.json'
    
    os.makedirs('data/raw', exist_ok=True)
    
    if os.path.exists(cache_file) and os.path.exists(index_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Проверяем свежесть кэша
            cache_time = cache_data.get('timestamp', 0)
            max_age_seconds = max_age_hours * 3600
            
            if time.time() - cache_time < max_age_seconds:
                articles = cache_data.get('articles', [])
                print(f"📂 CNews: Загружено {len(articles)} статей из кэша (свежесть: {max_age_hours}ч)")
                
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                
                return articles, index_data
            else:
                print(f"📂 CNews: Кэш устарел (> {max_age_hours} часов), обновляем...")
        except Exception as e:
            print(f"📂 CNews: Ошибка загрузки кэша: {e}")
    
    print("🔄 CNews: Создание нового кэша...")
    articles = parse_cnews_sitemaps(max_articles)
    index_data = build_search_index(articles)
    
    cache_data = {
        'timestamp': time.time(),
        'articles': articles,
        'count': len(articles),
        'source': 'sitemap_with_rules'
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 CNews: Сохранено {len(articles)} статей в кэш")
    return articles, index_data

def parse_cnews_sitemaps(max_articles=200):
    """Парсит sitemap с соблюдением правил"""
    sitemap_urls = [
        "https://www.cnews.ru/inc/sitemap.xml",
        "https://www.cnews.ru/inc/sitemap_book.xml",
    ]
    
    all_articles = []
    
    for sitemap_url in sitemap_urls:
        try:
            print(f"📡 CNews: Загрузка {sitemap_url.split('/')[-1]}...")
            
            # Уважительная пауза перед запросом
            time.sleep(random.uniform(2, 3))
            
            response = requests.get(sitemap_url, headers=HEADERS, timeout=15)
            
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                
                urls = root.findall('ns:url', namespace)
                print(f"  📄 Найдено {len(urls)} URL в sitemap")
                
                for url in urls:
                    loc = url.find('ns:loc', namespace)
                    if loc is not None:
                        article_url = loc.text.strip()
                        
                        # Фильтруем по robots.txt
                        if not is_url_allowed(article_url):
                            continue
                        
                        # Проверяем дату публикации (если есть)
                        lastmod = url.find('ns:lastmod', namespace)
                        if lastmod is not None:
                            try:
                                pub_date = datetime.fromisoformat(lastmod.text.replace('Z', '+00:00'))
                                # Берём статьи за последний год
                                if datetime.now() - pub_date > timedelta(days=365):
                                    continue
                            except:
                                pass
                        
                        all_articles.append(article_url)
                        
                        if len(all_articles) >= max_articles:
                            print(f"  ⏹️  Достигнут лимит {max_articles} статей")
                            break
                
                if len(all_articles) >= max_articles:
                    break
                    
            else:
                print(f"  ⚠️  Ошибка HTTP {response.status_code}")
                
            # Пауза между sitemap
            time.sleep(random.uniform(3, 4))
            
        except Exception as e:
            print(f"  ⚠️  Ошибка парсинга sitemap: {str(e)[:50]}")
            time.sleep(5)
            continue
    
    print(f"✅ CNews: Отфильтровано {len(all_articles)} разрешённых статей")
    return all_articles[:max_articles]

def parse_analytics_section(max_pages=3):
    """Парсит раздел аналитики (дополнительный источник)"""
    analytics_urls = []
    base_url = "https://www.cnews.ru/analytics/"
    
    try:
        # Главная страница аналитики
        time.sleep(random.uniform(3, 4))
        response = requests.get(base_url, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем ссылки на аналитические статьи
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(base_url, href)
                
                if '/analytics/' in full_url and is_url_allowed(full_url):
                    if full_url not in analytics_urls:
                        analytics_urls.append(full_url)
            
            print(f"📊 Analytics: Найдено {len(analytics_urls)} статей в разделе аналитики")
    
    except Exception as e:
        print(f"📊 Analytics: Ошибка парсинга: {e}")
    
    return analytics_urls[:max_pages * 10]  # Примерно 10 статей на страницу

def build_search_index(articles, batch_size=15):
    """Создает поисковый индекс с уважительными паузами"""
    print("📇 CNews: Построение поискового индекса...")
    
    index = {}
    indexed_count = 0
    
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i+batch_size]
        print(f"  📄 Индексируем статьи {i+1}-{i+len(batch)}/{len(articles)}...")
        
        for url in batch:
            try:
                if not is_url_allowed(url):
                    continue
                
                # Уважительная пауза
                time.sleep(random.uniform(1.5, 2.5))
                
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code != 200:
                    continue
                
                # Ограничиваем объём скачиваемых данных
                soup = BeautifulSoup(response.content[:50000], 'html.parser')
                
                # Извлекаем заголовок
                title_elem = soup.find('h1') or soup.find('title')
                title = title_elem.get_text(strip=True) if title_elem else ""
                
                if not title or len(title) < 10:
                    continue
                
                # Извлекаем дату
                date_text = ""
                for elem in soup.find_all(['time', 'span', 'div']):
                    if 'date' in elem.get('class', []) or 'time' in str(elem):
                        date_text = elem.get_text(strip=True)
                        break
                
                # Извлекаем ключевые слова из заголовка
                words = re.findall(r'\b[a-zA-Zа-яА-Я]{4,}\b', title.lower())
                for word in words:
                    if word not in index:
                        index[word] = []
                    
                    # Проверяем дубликаты
                    if not any(item['url'] == url for item in index[word]):
                        index[word].append({
                            'url': url,
                            'title': title[:120],
                            'date': date_text[:50],
                            'full_title': title
                        })
                
                indexed_count += 1
                
                # Небольшая пауза между статьями
                time.sleep(random.uniform(0.8, 1.2))
                
            except Exception as e:
                print(f"    ⚠️  Ошибка индексации {url[:50]}: {str(e)[:30]}")
                time.sleep(3)
                continue
        
        # Большая пауза между батчами
        if i + batch_size < len(articles):
            pause = random.uniform(4, 6)
            print(f"    ⏸️  Перерыв {pause:.1f}с")
            time.sleep(pause)
    
    print(f"✅ CNews: Индекс построен ({len(index)} ключевых слов, {indexed_count} статей)")
    return index

# ===================== ОПТИМИЗИРОВАННЫЙ ПОИСК =====================

def prepare_search_variants(company_name):
    """Подготавливает варианты для поиска"""
    name_lower = company_name.lower().strip()
    
    variants = []
    
    # Основное название
    variants.append(name_lower)
    
    # Упрощённые варианты (убираем юридические формы)
    legal_forms = ['банк', 'ооо', 'ао', 'пао', 'зао', 'групп', 'пром', 'российский', 'русский']
    words = name_lower.split()
    filtered_words = [w for w in words if w not in legal_forms and len(w) > 2]
    
    if filtered_words:
        simplified = ' '.join(filtered_words)
        if simplified != name_lower:
            variants.append(simplified)
    
    # Отдельные значимые слова
    for word in words:
        if len(word) > 3 and word not in legal_forms:
            variants.append(word)
    
    # Английские варианты
    english_map = {
        'тинькофф': 'tinkoff',
        'сбер': 'sber',
        'яндекс': 'yandex',
        'озон': 'ozon',
        'вильдберриз': 'wildberries',
        'мтс': 'mts',
        'билайн': 'beeline',
        'мегафон': 'megafon',
        'втб': 'vtb',
        'газпром': 'gazprom',
        'теле2': 'tele2',
        'ростелеком': 'rostelecom',
        'авито': 'avito',
        'ламода': 'lamoda'
    }
    
    for ru, en in english_map.items():
        if ru in name_lower:
            variants.append(en)
    
    # Уникальные варианты
    unique_variants = []
    for v in variants:
        if v and len(v) > 2 and v not in unique_variants:
            unique_variants.append(v)
    
    return unique_variants

def find_articles_by_company(company_name, index, max_results=8):
    """Быстрый поиск статей по компании через индекс"""
    search_variants = prepare_search_variants(company_name)
    
    found_articles = []
    seen_urls = set()
    
    # Ищем по ключевым словам в индексе
    for variant in search_variants:
        if variant in index:
            for article_info in index[variant]:
                url = article_info['url']
                if url not in seen_urls:
                    found_articles.append(article_info)
                    seen_urls.add(url)
                    
                    if len(found_articles) >= max_results:
                        break
        
        if len(found_articles) >= max_results:
            break
    
    return found_articles[:max_results]

def extract_support_numbers_from_text(text):
    """Ищет упоминания размеров команд поддержки в тексте"""
    patterns = [
        # Прямые упоминания команды поддержки
        r'(?:команд[ауе]|штат|сотрудник[а-я]*)\s*(?:поддержк[а-я]*|колл.?центр[а-я]*)\s*(?:из|в|более|около|до|свыше)?\s*(\d{2,})\s*(?:человек|сотрудник|специалист|оператор)',
        r'(\d{2,})\s*(?:оператор|специалист|сотрудник)\s*(?:в|работает|входит)\s*(?:в)?\s*(?:команд[ауе]|штат)?\s*(?:поддержк[а-я]*|колл.?центр[а-я]*)',
        
        # Расширение/найм
        r'(?:расширил[аи]?|увеличил[аи]?|нанял[аи]?|открыл[аи]?)\s*(?:команд[ауе]|штат|отдел)?\s*(?:поддержк[а-я]*|колл.?центр[а-я]*)\s*(?:до|на|более)\s*(\d{2,})\s*(?:человек|сотрудник)',
        r'(?:создал[аи]?|запустил[аи]?)\s*(?:новый)?\s*(?:колл.?центр|поддержк[ауе])\s*(?:на|в составе|с)\s*(\d{2,})\s*(?:оператор|специалист)',
        
        # Общие цифры в контексте поддержки
        r'(?:поддержк[а-я]+|обслуживани[ея])\s*(?:клиент[а-я]*|пользовател[а-я]*)\s*(?:осуществляет|обеспечивает|производит)[^.]{0,100}?(\d{2,})\s*(?:сотрудник|специалист)',
    ]
    
    findings = []
    text_lower = text.lower()
    
    for pattern in patterns:
        matches = re.finditer(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            try:
                num = int(match.group(1))
                if 10 <= num <= 10000:  # Реалистичный диапазон
                    # Берем контекст
                    start = max(0, match.start() - 60)
                    end = min(len(text_lower), match.end() + 60)
                    context = text_lower[start:end].replace('\n', ' ').strip()
                    
                    findings.append({
                        'value': num,
                        'text': context,
                        'match': match.group(0),
                        'pattern': pattern[:30]
                    })
                    
                    # Ограничиваем количество находок
                    if len(findings) >= 3:
                        break
            except (ValueError, IndexError):
                continue
        if len(findings) >= 3:
            break
    
    return findings

def search_cnews_for_company_fast(company_name, articles, index, max_articles=8):
    """Быстрый поиск для одной компании с соблюдением правил"""
    print(f"  📰 Поиск: {company_name[:25]}...", end=' ')
    
    # 1. Поиск релевантных статей через индекс
    relevant_articles = find_articles_by_company(company_name, index, max_results=max_articles)
    
    if not relevant_articles:
        print(f"➖ нет статей")
        return []
    
    print(f"найдено {len(relevant_articles)} статей")
    
    # 2. Глубокий анализ только релевантных статей
    findings = []
    
    for i, article_info in enumerate(relevant_articles):
        try:
            # Проверяем URL
            if not is_url_allowed(article_info['url']):
                continue
            
            # Уважительная пауза
            delay = random.uniform(2, 4)
            time.sleep(delay)
            
            print(f"    [{i+1}/{len(relevant_articles)}] Анализ статьи...")
            
            response = requests.get(article_info['url'], headers=HEADERS, timeout=12)
            if response.status_code != 200:
                print(f"      ⚠️  HTTP {response.status_code}")
                time.sleep(3)
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Удаляем скрипты и стили
            for element in soup(["script", "style", "iframe", "nav", "footer"]):
                element.decompose()
            
            # Получаем основной текст
            main_content = soup.find('article') or soup.find('div', class_=re.compile(r'(content|article|text)'))
            
            if main_content:
                text = main_content.get_text(' ', strip=True)
            else:
                text = soup.get_text(' ', strip=True)
            
            # Ограничиваем длину текста для анализа
            text_sample = text[:10000]
            
            # Ищем доказательства
            article_findings = extract_support_numbers_from_text(text_sample)
            
            if article_findings:
                # Берём максимальное значение
                best_finding = max(article_findings, key=lambda x: x['value'])
                
                findings.append({
                    'type': 'CNEWS_ARTICLE',
                    'value': best_finding['value'],
                    'text': best_finding['match'][:150],
                    'context': best_finding['text'][:200],
                    'url': article_info['url'],
                    'title': article_info.get('full_title', article_info['title']),
                    'date': article_info.get('date', ''),
                    'source': 'cnews',
                    'company': company_name,
                    'timestamp': datetime.now().isoformat()
                })
                
                print(f"      ✅ Найдено: {best_finding['value']} чел.")
                
                # Увеличенная пауза после успешного парсинга
                time.sleep(random.uniform(3, 5))
                
            else:
                print(f"      ➖ Цифр не найдено")
                time.sleep(random.uniform(2, 3))
            
            # Перерыв каждые 3 статьи
            if (i + 1) % 3 == 0 and i < len(relevant_articles) - 1:
                pause = random.uniform(5, 7)
                print(f"    ⏸️  Перерыв {pause:.1f}с")
                time.sleep(pause)
                
        except requests.exceptions.RequestException as e:
            print(f"      ⚠️  Сетевая ошибка: {str(e)[:30]}")
            time.sleep(10)  # Долгая пауза при сетевых ошибках
            continue
        except Exception as e:
            print(f"      ⚠️  Ошибка: {str(e)[:30]}")
            time.sleep(5)
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
            CNEWS_CACHE, CNEWS_INDEX = load_or_create_cnews_cache(
                max_articles=150,
                max_age_hours=24
            )
        
        if not CNEWS_CACHE or not CNEWS_INDEX:
            print("➖ (нет данных)")
            return existing_findings
        
        # Пауза перед поиском
        time.sleep(random.uniform(2, 3))
        
        # Быстрый поиск
        cnews_findings = search_cnews_for_company_fast(
            company_name, 
            CNEWS_CACHE, 
            CNEWS_INDEX,
            max_articles=6  # Уменьшили для скорости и вежливости
        )
        
        if cnews_findings:
            print(f"✅ найдено {len(cnews_findings)} доказательств")
            
            # Объединяем результаты
            all_findings = existing_findings + cnews_findings
            
            # Дополнительная пауза после успешного поиска
            time.sleep(random.uniform(2, 4))
            
            return all_findings
        else:
            print("➖ не найдено")
            time.sleep(random.uniform(1, 2))
            return existing_findings
        
    except Exception as e:
        print(f"⚠️ ошибка: {str(e)[:30]}")
        # Небольшая пауза при ошибке
        time.sleep(random.uniform(3, 5))
        return existing_findings

# ===================== ТЕСТИРОВАНИЕ =====================

def test_cnews_compliance():
    """Тест соблюдения правил robots.txt"""
    print("\n🧪 Тест соблюдения правил CNews")
    print("=" * 60)
    
    test_urls = [
        "https://www.cnews.ru/news/for_blog/test",  # Должен быть запрещён
        "https://www.cnews.ru/news/2024-01-01/test",  # Должен быть разрешён
        "https://www.cnews.ru/articles/for_print/test",  # Должен быть запрещён
        "https://www.cnews.ru/analytics/report",  # Должен быть разрешён
        "https://www.cnews.ru/search?q=test",  # Должен быть запрещён
    ]
    
    for url in test_urls:
        allowed = is_url_allowed(url)
        status = "✅ РАЗРЕШЁН" if allowed else "❌ ЗАПРЕЩЁН"
        print(f"{status}: {url}")
    
    print("\n📊 Загрузка кэша...")
    articles, index = load_or_create_cnews_cache(max_articles=50)
    
    # Проверяем, что все статьи разрешены
    disallowed_count = 0
    for url in articles:
        if not is_url_allowed(url):
            disallowed_count += 1
    
    print(f"📊 Статистика кэша:")
    print(f"  • Всего статей: {len(articles)}")
    print(f"  • Запрещённых: {disallowed_count}")
    print(f"  • Соответствие robots.txt: {100 - (disallowed_count/len(articles)*100):.1f}%")
    
    return articles, index

def test_search_for_companies(companies, limit=5):
    """Тестирует поиск для нескольких компаний"""
    print(f"\n🔍 Тест поиска для {min(limit, len(companies))} компаний")
    print("=" * 60)
    
    articles, index = load_or_create_cnews_cache(max_articles=100)
    
    results = {}
    
    for i, company in enumerate(companies[:limit]):
        company_name = company['name'] if isinstance(company, dict) else company
        
        print(f"\n[{i+1}/{min(limit, len(companies))}] {company_name}")
        
        # Пауза между компаниями
        if i > 0:
            time.sleep(random.uniform(4, 6))
        
        findings = search_cnews_for_company_fast(company_name, articles, index, max_articles=5)
        results[company_name] = findings
        
        if findings:
            print(f"   ✅ Найдено: {len(findings)} доказательств")
            for f in findings[:2]:
                print(f"      • {f['value']} чел.: {f['text'][:60]}...")
        else:
            print(f"   ➖ Не найдено")
    
    # Статистика
    companies_with_findings = [c for c, f in results.items() if f]
    
    print(f"\n📊 Итоговая статистика:")
    print(f"   • Компаний с находками: {len(companies_with_findings)}/{len(results)}")
    print(f"   • Всего находок: {sum(len(f) for f in results.values())}")
    print(f"   • Эффективность: {len(companies_with_findings)/len(results)*100:.1f}%")
    
    return results

if __name__ == "__main__":
    # Тест соответствия правилам
    test_cnews_compliance()
    
    # Тест поиска
    test_companies = ["Сбербанк", "Тинькофф", "МТС", "Яндекс", "ВТБ"]
    test_search_for_companies(test_companies, limit=5)