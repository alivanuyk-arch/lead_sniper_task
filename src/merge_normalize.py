"""Анализ находок, принятие решений и нормализация данных - с поддержкой CNews"""
import re

# Нормы нагрузки по отраслям (ваша логика)
INDUSTRY_NORMS = {
    'bank': {'ratio': 2000, 'min': 50},
    'telecom': {'ratio': 5000, 'min': 40},
    'marketplace': {'ratio': 10000, 'min': 30},
    'delivery': {'ratio': 8000, 'min': 25},
    'insurance': {'ratio': 30000, 'min': 30},
    'retail': {'ratio': 50000, 'min': 20},
    'restaurant': {'ratio': 20000, 'min': 15},
    'it': {'ratio': 500, 'min': 10},
    'saas': {'ratio': 300, 'min': 10},
    'cloud': {'ratio': 200, 'min': 10},
    'callcenter': {'ratio': 50, 'min': 50},
    'default': {'ratio': 1000, 'min': 10}
}

def analyze_company_findings(all_findings, hh_vacancies, company_data):
    """Анализирует ВСЕ находки (сайт + CNews + HH) и принимает решение"""
    
    # Разделяем находки по источникам
    website_findings = [f for f in all_findings if f.get('source') == 'website']
    cnews_findings = [f for f in all_findings if f.get('source') == 'cnews']
    
    # Добавляем находки из HH вакансий
    for vacancy in hh_vacancies:
        desc = vacancy.get('description', '')
        
        if re.search(r'(\d{2,})\s*(?:человек|сотрудник|специалист)', desc, re.IGNORECASE):
            all_findings.append({
                'type': 'TEAM_SIZE_DIRECT',
                'text': desc[:100],
                'source': 'hh_vacancy',
                'url': vacancy.get('url', '')
            })
        
        if re.search(r'24/7|круглосуточно|сменн.*?график', desc, re.IGNORECASE):
            all_findings.append({
                'type': '24_7',
                'text': 'Круглосуточная работа (из вакансии)',
                'source': 'hh_vacancy'
            })
    
    # Группируем находки по типам
    findings_by_type = {}
    for finding in all_findings:
        ftype = finding.get('type')
        if ftype not in findings_by_type:
            findings_by_type[ftype] = []
        findings_by_type[ftype].append(finding)
    
    # ========== НОВАЯ ЛОГИКА: СНАЧАЛА CNEWS ==========
    
    # 1. УРОВЕНЬ A++: Прямые цифры из CNews (высший приоритет)
    if 'CNEWS_ARTICLE' in findings_by_type:
        cnews_sizes = [f.get('value', 0) for f in findings_by_type['CNEWS_ARTICLE']]
        if cnews_sizes:
            max_cnews = max(cnews_sizes)
            best_cnews = max(findings_by_type['CNEWS_ARTICLE'], 
                           key=lambda x: x.get('value', 0))
            
            return {
                'support_team_size_min': max_cnews,
                'support_evidence': f"CNews: '{best_cnews.get('text', '')[:100]}'",
                'evidence_url': best_cnews.get('url', ''),
                'evidence_type': 'cnews',
                'decision_logic': 'LEVEL_A++_CNEWS_DIRECT'
            }
    
    # 2. УРОВЕНЬ A: Прямые цифры с сайта или HH
    if 'TEAM_SIZE_DIRECT' in findings_by_type:
        direct_sizes = []
        for finding in findings_by_type['TEAM_SIZE_DIRECT']:
            if finding.get('value'):
                direct_sizes.append(finding['value'])
        
        if direct_sizes:
            max_size = max(direct_sizes)
            best_finding = max(findings_by_type['TEAM_SIZE_DIRECT'], 
                             key=lambda x: x.get('value', 0))
            
            source_type = 'site' if best_finding.get('source') == 'website' else 'jobs'
            return {
                'support_team_size_min': max_size,
                'support_evidence': f"Прямое упоминание: '{best_finding['text'][:100]}'",
                'evidence_url': best_finding.get('url', f"https://{company_data.get('site', '')}"),
                'evidence_type': source_type,
                'decision_logic': 'LEVEL_A_DIRECT'
            }
    
    # 3. УРОВЕНЬ B: Расчёт через клиентскую базу (любой источник)
    if 'CLIENT_SCALE' in findings_by_type:
        client_finding = max(findings_by_type['CLIENT_SCALE'], 
                           key=lambda x: x.get('value_millions', 0))
        
        clients_millions = client_finding.get('value_millions', 0)
        clients_total = clients_millions * 1_000_000
        
        category = company_data.get('category', 'default')
        norm = INDUSTRY_NORMS.get(category, INDUSTRY_NORMS['default'])
        
        calculated = max(10, int(clients_total / norm))
        if calculated > 1000:
            calculated = 1000
        
        return {
            'support_team_size_min': calculated,
            'support_evidence': f"Расчёт: {clients_millions} млн клиентов",
            'evidence_url': client_finding.get('url', f"https://{company_data.get('site', '')}"),
            'evidence_type': 'site',
            'decision_logic': 'LEVEL_B_CLIENT_CALCULATION'
        }
    
    # 4. УРОВЕНЬ B: 24/7 + смены (любой источник)
    has_24_7 = '24_7' in findings_by_type
    has_shifts = 'SHIFT_WORK' in findings_by_type
    
    if has_24_7 and has_shifts:
        evidence_url = ''
        if findings_by_type['24_7']:
            evidence_url = findings_by_type['24_7'][0].get('url', '')
        
        return {
            'support_team_size_min': 12,
            'support_evidence': "Круглосуточная работа со сменным графиком",
            'evidence_url': evidence_url or f"https://{company_data.get('site', '')}",
            'evidence_type': 'site',
            'decision_logic': 'LEVEL_B_24_7_SHIFT'
        }
    
    # 5. УРОВЕНЬ B: Только 24/7
    if has_24_7:
        return {
            'support_team_size_min': 10,
            'support_evidence': "Круглосуточная работа поддержки",
            'evidence_url': findings_by_type['24_7'][0].get('url', f"https://{company_data.get('site', '')}"),
            'evidence_type': 'site',
            'decision_logic': 'LEVEL_B_24_7_ONLY'
        }
    
    # 6. Если много вакансий поддержки
    if len(hh_vacancies) >= 3:
        return {
            'support_team_size_min': max(10, len(hh_vacancies) * 2),
            'support_evidence': f"Найдено {len(hh_vacancies)} вакансий поддержки",
            'evidence_url': 'https://hh.ru',
            'evidence_type': 'jobs',
            'decision_logic': 'LEVEL_B_MULTIPLE_VACANCIES'
        }
    
    # 7. Если есть находки CNews (даже без цифр)
    if cnews_findings:
        return {
            'support_team_size_min': 8,
            'support_evidence': f"Упоминание в CNews: {cnews_findings[0].get('title', '')[:80]}",
            'evidence_url': cnews_findings[0].get('url', ''),
            'evidence_type': 'cnews',
            'decision_logic': 'LEVEL_C_CNEWS_MENTION'
        }
    
    return None

def normalize_record(record):
    """Нормализует запись для CSV"""
    if not record:
        return None
    
    # Нормализация ИНН (строка)
    if 'inn' in record:
        record['inn'] = str(record['inn']).strip()
    
    # Нормализация сайта
    if 'site' in record and record['site']:
        site = record['site'].lower().strip()
        if not site.startswith(('http://', 'https://')):
            record['site'] = f"https://{site}"
    
    # Булевы поля в 0/1
    bool_fields = [
        'has_support_email', 'has_contact_form', 'has_online_chat',
        'has_messengers', 'has_support_section', 'has_kb_or_faq', 
        'mentions_24_7', 'has_cnews_evidence'
    ]
    
    for field in bool_fields:
        if field in record:
            record[field] = 1 if record.get(field) else 0
    
    # Обеспечиваем обязательные поля
    required_fields = ['support_team_size_min', 'support_evidence', 'evidence_url']
    for field in required_fields:
        if field not in record:
            record[field] = 0 if field == 'support_team_size_min' else ''
    
    return record

# ========== ФУНКЦИИ ДЛЯ БУЛЕВЫХ ПРИЗНАКОВ ==========
# (Оставляем без изменений)

def check_support_email(findings):
    for finding in findings:
        if finding.get('type') == 'SUPPORT_EMAIL':
            return True
    return False

def check_contact_form(findings):
    for finding in findings:
        if finding.get('type') == 'CONTACT_FORM':
            return True
    return False

def check_online_chat(findings):
    for finding in findings:
        if finding.get('type') == 'ONLINE_CHAT':
            return True
    return False

def check_messengers(findings):
    for finding in findings:
        text = finding.get('text', '').lower()
        if any(messenger in text for messenger in ['telegram', 'whatsapp', 'viber']):
            return True
    return False

def check_support_section(findings):
    support_pages = ['поддержка', 'help', 'support', 'помощь', 'контакты']
    for finding in findings:
        page = finding.get('page', '').lower()
        if any(page_name in page for page_name in support_pages):
            return True
    return False

def check_kb_faq(findings):
    for finding in findings:
        if finding.get('type') == 'FAQ_KB':
            return True
    return False