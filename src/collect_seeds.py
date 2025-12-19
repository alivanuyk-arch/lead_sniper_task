import json
import os

def load_company_base(filepath='data/company_base.json'):
    """Загружает базовый список компаний из JSON"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            companies = json.load(f)
            print(f"✅ Загружено {len(companies)} компаний из {filepath}")
            return companies
    except FileNotFoundError:
        print(f"❌ Файл {filepath} не найден")
        return []
    except json.JSONDecodeError:
        print(f"❌ Ошибка чтения JSON из {filepath}")
        return []

def filter_valid_companies(companies):
    """Фильтрует компании с обязательными полями"""
    valid = []
    for company in companies:
        if all(key in company for key in ['inn', 'name', 'site']):
            valid.append(company)
    return valid