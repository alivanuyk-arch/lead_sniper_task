"""Парсинг сайтов компаний - поиск доказательств поддержки"""
import requests
import re
import time
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# ========== ФУНКЦИИ ПОИСКА ДОКАЗАТЕЛЬСТВ (ВЗЯТЫ ИЗ ВАШЕГО КОДА) ==========

def find_team_size_numbers(text):
    """Ищет ПРЯМЫЕ упоминания размера команды поддержки (Уровень A)"""
    patterns = [
        r'(\d{2,})\s*(?:человек|сотрудник|специалист|оператор|агент).*?(?:поддержк|кол?[- ]?центр)',
        r'(?:поддержк|кол?[- ]?центр).*?(\d{2,})\s*(?:человек|сотрудник)',
        r'штат\s*.*?(\d{2,})\s*(?:сотрудник|человек)',
        r'команда\s*.*?(\d{2,})\s*(?:человек|сотрудник)',
        r'(\d{2,})\s*оператор.*?(?:поддержк|кол?центр)'
    ]
    
    findings = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                num = int(match.group(1))
                if num >= 10:
                    findings.append({
                        'type': 'TEAM_SIZE_DIRECT',
                        'value': num,
                        'text': match.group(0)[:150]
                    })
            except (ValueError, IndexError):
                continue
    return findings

def find_24_7_evidence(text):
    """Ищет доказательства круглосуточной работы (Уровень B)"""
    patterns = [
        r'24/7|24\s*часа|круглосуточно',
        r'работаем\s*(?:круглосуточно|24|без\s*выходных)',
        r'поддержка\s*(?:круглосуточная|24/7)',
        r'всегда\s*на\s*связи',
        r'служба\s*поддержки\s*(?:работает\s*)?круглосуточно'
    ]
    
    findings = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings.append({
                'type': '24_7',
                'text': match.group(0)
            })
    return findings

def find_shift_patterns(text):
    """Ищет сменный график (Уровень B)"""
    patterns = [
        r'график\s*(?:2/2|3/3|сменный|скользящий)',
        r'сменн.*?(?:график|работа|расписание)',
        r'ночн.*?(?:смен|дежурств|работа)',
        r'работа\s*(?:в\s*смены|по\s*сменам|посменно)',
        r'(?:день/ночь|утро/вечер)'
    ]
    
    findings = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings.append({
                'type': 'SHIFT_WORK',
                'text': match.group(0)
            })
    return findings

def find_client_scale(text):
    """Ищет масштаб клиентской базы (для расчёта Уровень B)"""
    patterns = [
        r'(\d+(?:[.,]\d+)?)\s*(?:млн|миллион|тыс|тысяч).*?(?:клиент|пользователь|абонент)',
        r'более\s*(\d+(?:[.,]\d+)?)\s*(?:млн|миллион).*?(?:клиент|пользователь)',
        r'аудитория\s*.*?(\d+(?:[.,]\d+)?)\s*(?:млн|миллион)',
        r'обслуживаем\s*.*?(\d+(?:[.,]\d+)?)\s*(?:млн|миллион)'
    ]
    
    findings = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                num_str = match.group(1).replace(',', '.')
                num = float(num_str)
                
                if any(word in match.group(0).lower() for word in ['тыс', 'тысяч']):
                    num = num / 1000
                
                findings.append({
                    'type': 'CLIENT_SCALE',
                    'value_millions': num,
                    'text': match.group(0)[:150]
                })
            except (ValueError, AttributeError):
                continue
    return findings

def find_contact_features(text):
    """Ищет признаки каналов поддержки (для булевых полей)"""
    findings = []
    
    # Онлайн-чат
    if re.search(r'онлайн.?чат|live.?chat|чат\s*с\s*оператором', text, re.IGNORECASE):
        findings.append({'type': 'ONLINE_CHAT', 'text': 'Найден онлайн-чат'})
    
    # Форма обратной связи
    if re.search(r'форма\s*обратной|обратная\s*связь|задать\s*вопрос', text, re.IGNORECASE):
        findings.append({'type': 'CONTACT_FORM', 'text': 'Найдена форма обратной связи'})
    
    # FAQ/База знаний
    if re.search(r'faq|часто\s*задаваем|база\s*знаний|вопрос.?ответ', text, re.IGNORECASE):
        findings.append({'type': 'FAQ_KB', 'text': 'Найден FAQ/база знаний'})
    
    # Email поддержки
    if re.search(r'support@|help@|поддержка@|обратная@', text, re.IGNORECASE):
        findings.append({'type': 'SUPPORT_EMAIL', 'text': 'Найден email поддержки'})
    
    return findings

# ========== ОСНОВНАЯ ФУНКЦИЯ ПАРСИНГА ==========

def parse_website(domain, max_pages=5):
    """Парсит сайт компании и возвращает все находки"""
    pages_to_check = [
        ('', 'главная'),
        ('/about', 'о компании'),
        ('/support', 'поддержка'),
        ('/help', 'помощь'),
        ('/contact', 'контакты'),
        ('/career', 'карьера'),
        ('/jobs', 'вакансии')
    ]
    
    all_findings = []
    pages_checked = 0
    
    for path, page_name in pages_to_check[:max_pages]:
        try:
            if path:
                url = f"https://{domain}{path}"
            else:
                url = f"https://{domain}"
            
            response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            page_text = soup.get_text()
            
            # Ищем ВСЕ типы доказательств
            findings = []
            findings.extend(find_team_size_numbers(page_text))
            findings.extend(find_24_7_evidence(page_text))
            findings.extend(find_shift_patterns(page_text))
            findings.extend(find_client_scale(page_text))
            findings.extend(find_contact_features(page_text))
            
            for finding in findings:
                finding.update({
                    'source': 'website',
                    'page': page_name,
                    'url': url
                })
            
            all_findings.extend(findings)
            pages_checked += 1
            
            time.sleep(2)  # Пауза между запросами
            
        except Exception as e:
            continue
    
    return all_findings