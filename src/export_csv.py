"""Экспорт данных в CSV"""
import csv
import os
from datetime import datetime

CSV_FIELDNAMES = [
    # ОБЯЗАТЕЛЬНЫЕ ПО ТЗ
    'inn', 'name', 'site', 'support_team_size_min', 'support_evidence',
    'evidence_url', 'evidence_type', 'source',
    'has_support_email', 'has_contact_form', 'has_online_chat',
    'has_messengers', 'has_support_section', 'has_kb_or_faq', 'mentions_24_7',
    
    # ЖЕЛАТЕЛЬНЫЕ ПО ТЗ
    'revenue', 'employees', 'okved_main', 'support_email',
    'support_url', 'kb_url', 'chat_vendor'
]

def save_to_csv(records, filename='data/companies.csv'):
    """Сохраняет записи в CSV файл"""
    
    # Создаём папку если нет
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # Сохраняем с timestamp backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"data/companies_backup_{timestamp}.csv"
    
    saved_files = []
    
    # Сохраняем основной файл
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        
        for record in records:
            # Заполняем только существующие поля
            row = {}
            for field in CSV_FIELDNAMES:
                row[field] = record.get(field, '')
            writer.writerow(row)
    
    saved_files.append(filename)
    
    # Делаем backup
    try:
        import shutil
        shutil.copy2(filename, backup_filename)
        saved_files.append(backup_filename)
    except:
        pass
    
    print(f"💾 Сохранено {len(records)} компаний")
    print(f"📁 Основной файл: {filename}")
    if len(saved_files) > 1:
        print(f"📁 Backup: {backup_filename}")
    
    return filename

def load_csv(filename='data/companies.csv'):
    """Загружает данные из CSV"""
    if not os.path.exists(filename):
        return []
    
    records = []
    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    
    return records