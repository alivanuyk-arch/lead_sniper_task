
"""Парсинг вакансий с HH API"""
import requests
import re
import time

HH_API_URL = "https://api.hh.ru"

def search_hh_vacancies(company_name):
    """Ищет вакансии компании на HH и анализирует описания"""
    vacancies_data = []
    
    try:
        # 1. Поиск работодателя
        search_url = f"{HH_API_URL}/employers"
        params = {'text': company_name, 'per_page': 1}
        
        response = requests.get(search_url, params=params, timeout=10)
        if response.status_code != 200:
            return vacancies_data
        
        employers = response.json().get('items', [])
        if not employers:
            return vacancies_data
        
        employer_id = employers[0]['id']
        
        # 2. Поиск вакансий с ключевыми словами поддержки
        vac_url = f"{HH_API_URL}/vacancies"
        params = {
            'employer_id': employer_id,
            'text': 'поддержка OR оператор OR колл-центр OR customer support OR helpdesк',
            'per_page': 10,
            'area': 113  # Россия
        }
        
        vac_response = requests.get(vac_url, params=params, timeout=10)
        if vac_response.status_code != 200:
            return vacancies_data
        
        vacancies = vac_response.json().get('items', [])
        
        # 3. Собираем данные по вакансиям
        for vacancy in vacancies:
            vacancy_info = {
                'id': vacancy.get('id'),
                'name': vacancy.get('name', ''),
                'url': vacancy.get('alternate_url', ''),
                'description': f"{vacancy.get('snippet', {}).get('requirement', '')} "
                             f"{vacancy.get('snippet', {}).get('responsibility', '')}"
            }
            vacancies_data.append(vacancy_info)
        
        time.sleep(0.5)  # Уважаем лимиты HH API
        
    except Exception as e:
        print(f"⚠️ Ошибка HH API для {company_name}: {e}")
    
    return vacancies_data