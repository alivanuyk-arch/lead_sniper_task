"""
синхронный парсинг сайтов с умным поиском разделов поддержки
"""
import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'ru-RU,ru;q=0.9',
}

async def fetch_page(session, url, timeout=8):
    """синхронная загрузка страницы"""
    try:
        async with session.get(url, headers=HEADERS, timeout=timeout, ssl=False) as response:
            if response.status == 200:
                html = await response.text()
                # роверяем, что это не ошибка 404/редирект на главную
                if len(html) > 500:  # инимум контента
                    return html
    except:
        pass
    return None

async def check_support_sections(session, domain):
    """
    мная проверка разделов поддержки
    озвращает список найденных разделов
    """
    # опулярные пути разделов поддержки в российских компаниях
    support_paths = [
        '/support', '/help', '/contacts', '/contact',
        '/faq', '/feedback', '/service', '/client',
        '/customers', '/service-center', '/helpdesk',
        '/support-center', '/contact-us', '/obratnaya-svyaz'
    ]
    
    # Сначала проверяем самые вероятные
    priority_paths = ['/support', '/help', '/contacts']
    
    found_sections = []
    
    # роверяем приоритетные пути
    for path in priority_paths:
        url = f"https://{domain}{path}"
        html = await fetch_page(session, url)
        
        if html:
            # роверяем контент на признаки поддержки
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text().lower()
            
            support_keywords = ['поддерж', 'help', 'support', 'контакт', 'чат', 'вопрос', 'ответ']
            has_support = any(keyword in text for keyword in support_keywords)
            
            if has_support:
                found_sections.append(path)
                print(f"    🔍 айден раздел: {path}")
    
    # сли нашли хотя бы один раздел - останавливаемся
    if found_sections:
        return found_sections
    
    # сли нет - проверяем остальные пути
    tasks = []
    for path in support_paths[len(priority_paths):8]:  # ервые 8 всего
        url = f"https://{domain}{path}"
        tasks.append(fetch_page(session, url))
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    for path, html in zip(support_paths[len(priority_paths):8], responses):
        if html and not isinstance(html, Exception):
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text().lower()
            
            if any(kw in text for kw in ['поддерж', 'help', 'support']):
                found_sections.append(path)
                print(f"    🔍 айден раздел: {path}")
    
    return found_sections

async def parse_support_section(session, domain, path):
    """Парсим конкретный раздел поддержки - УЛУЧШЕННАЯ ВЕРСИЯ"""
    url = f"https://{domain}{path}"
    html = await fetch_page(session, url)
    
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Удаляем скрипты и стили для чистого текста
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()
    
    text = soup.get_text()
    text_lower = text.lower()
    
    findings = []
    features = []
    
    # 1. Ищем размер команды поддержки (Уровень A)
    team_patterns = [
        r'(\d{2,})\s*(?:человек|сотрудник|специалист|оператор|агент).*?поддержк',
        r'поддержк.*?(\d{2,})\s*(?:человек|сотрудник|специалист)',
        r'команда.*?(\d{2,})\s*(?:человек|сотрудник).*?поддержк',
        r'(\d{2,})\s*оператор.*?поддержк',
        r'штат.*?(\d{2,})\s*(?:человек|сотрудник).*?поддержк',
    ]
    
    for pattern in team_patterns:
        matches = re.finditer(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            try:
                num = int(match.group(1))
                if 10 <= num <= 10000:  # Реалистичный диапазон
                    findings.append({
                        'type': 'TEAM_SIZE',
                        'value': num,
                        'text': match.group(0)[:100],
                        'url': url,
                        'path': path
                    })
                    break  # Нашли одно - достаточно
            except:
                continue
    
    # 2. Ищем признаки поддержки (для булевых полей CSV)
    
    # 24/7
    if re.search(r'24/7|24\s*часа|круглосуточно|работаем\s*круглосуточно', text_lower):
        features.append('24/7')
    
    # Онлайн-чат
    if re.search(r'онлайн.?чат|live.?chat|чат\s*с\s*оператором|online.?chat', text_lower):
        features.append('чат')
    
    # Форма обратной связи
    if re.search(r'форма\s*обратной|обратная\s*связь|задать\s*вопрос|написать\s*нам', text_lower):
        features.append('форма')
    
    # FAQ/База знаний
    if re.search(r'faq|часто\s*задаваем|база\s*знаний|вопрос.?ответ|инструкци', text_lower):
        features.append('faq')
    
    # Email поддержки
    if re.search(r'support@|help@|поддержка@|обратная@|service@', text_lower):
        features.append('email')
    
    # Мессенджеры
    if re.search(r'telegram|whatsapp|viber|мессенджер|telegram', text_lower):
        features.append('мессенджеры')
    
    # Раздел поддержки (по заголовкам)
    headings = soup.find_all(['h1', 'h2', 'h3'])
    for heading in headings:
        heading_text = heading.get_text().lower()
        if any(word in heading_text for word in ['поддерж', 'help', 'support', 'контакт', 'помощь']):
            features.append('раздел_поддержки')
            break
    
    return {
        'findings': findings,
        'features': list(set(features)),  # Уникальные значения
        'url': url,
        'path': path
    }

async def analyze_company_website(session, domain):
    """
    сновная функция анализа сайта компании
    озвращает структурированные данные
    """
    print(f"    🔍 роверяем: https://{domain}")
    
    # 1. щем разделы поддержки
    support_sections = await check_support_sections(session, domain)
    
    if not support_sections:
        # роверяем главную страницу как fallback
        print(f"    🔍 роверяем главную страницу")
        main_url = f"https://{domain}"
        main_html = await fetch_page(session, main_url)
        
        if main_html:
            soup = BeautifulSoup(main_html, 'html.parser')
            text = soup.get_text().lower()
            
            # щем ссылки на поддержку в меню
            support_links = []
            for link in soup.find_all('a', href=True):
                href = link['href'].lower()
                link_text = link.get_text().lower()
                
                if any(kw in href or kw in link_text for kw in ['поддерж', 'help', 'support', 'контакт']):
                    # звлекаем путь
                    if href.startswith('/'):
                        support_links.append(href)
                    elif domain in href:
                        # бсолютный URL, извлекаем путь
                        import urllib.parse
                        parsed = urllib.parse.urlparse(href)
                        if parsed.path:
                            support_links.append(parsed.path)
            
            # никальные пути
            support_sections = list(set(support_links))[:3]
    
    # 2. арсим найденные разделы
    all_findings = []
    all_features = []
    
    if support_sections:
        tasks = []
        for path in support_sections[:3]:  # аксимум 3 раздела
            tasks.append(parse_support_section(session, domain, path))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, dict):
                all_findings.extend(result['findings'])
                all_features.extend(result['features'])
    
    # 3. ормируем результат
    evidence_parts = []
    
    if all_findings:
        # ерём максимальное найденное значение
        max_finding = max(all_findings, key=lambda x: x['value'])
        evidence_parts.append(f"сайт: прямое упоминание {max_finding['value']} чел.")
    
    if all_features:
        unique_features = list(set(all_features))
        evidence_parts.append(f"сайт: есть {', '.join(unique_features[:3])}")
    
    return {
        'found_sections': support_sections,
        'team_size_findings': all_findings,
        'features': all_features,
        'evidence': evidence_parts
    }
