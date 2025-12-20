import asyncio
import aiohttp
from bs4 import BeautifulSoup



HEADERS = {'User-Agent': 'Mozilla/5.0'}

async def fetch_website(session, domain):
    """Асинхронный запрос к сайту с проверкой КЛЮЧЕВЫХ разделов"""
    try:
        # Список возможных разделов поддержки
        support_pages = [
            '',              # главная
            '/help',         # помощь
            '/support',      # поддержка
            '/contact',      # контакты
            '/contacts',     # контакты (альт)
            '/service',      # сервис
            '/faq',          # FAQ
            '/pomosh',       # помощь (рус)
            '/klinentam',    # клиентам
            '/customers',    # клиенты
            '/obrashenie',   # обращение
            '/feedback',     # обратная связь
            '/vopros-otvet', # вопросы-ответы
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        }
        
        all_text = ""
        found_pages = []
        
        # Проверяем основные разделы (первые 5)
        for page in support_pages[:5]:
            try:
                url = f"https://{domain}{page}" if page else f"https://{domain}"
                print(f"    🔍 Проверяем: {url}")
                
                async with session.get(url, timeout=8, ssl=False, headers=headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Проверяем на блокировку
                        if any(blocked in html.lower() for blocked in ['cloudflare', 'access denied', '403', 'бот', 'captcha']):
                            continue
                        
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Удаляем скрипты
                        for script in soup(["script", "style", "noscript"]):
                            script.decompose()
                        
                        text = soup.get_text(separator=' ', strip=True)
                        
                        # Проверяем, есть ли признаки поддержки
                        support_keywords = ['поддерж', 'help', 'support', 'контакт', 'обращен', 'чат', 'телефон']
                        if any(kw in text.lower() for kw in support_keywords):
                            found_pages.append(page or '/')
                            all_text += " " + text
                            print(f"      ✅ Раздел найден: {page or '/'}")
                
                await asyncio.sleep(0.5)  # Маленькая пауза
                
            except Exception as e:
                continue
        
        # Если нашли хоть что-то
        if all_text:
            print(f"    📊 Найдено разделов: {len(found_pages)}")
            print(f"    📝 Общий текст: {len(all_text)} символов")
            return all_text
        else:
            print(f"    ⚠️ Разделы поддержки не найдены")
            return ""
                
    except Exception as e:
        print(f"    ⚠️ Ошибка: {str(e)[:50]}")
        return ""

async def fetch_hh_vacancies(session, company_name):
    """Асинхронный запрос к HH API"""
    try:
        # Поиск работодателя
        search_url = "https://api.hh.ru/employers"
        params = {'text': company_name, 'per_page': 1}
        
        async with session.get(search_url, params=params, timeout=10) as response:
            if response.status != 200:
                return []
            data = await response.json()
            if not data.get('items'):
                return []
            
            employer_id = data['items'][0]['id']
            
            # Поиск вакансий
            vac_url = f"https://api.hh.ru/vacancies"
            params = {
                'employer_id': employer_id,
                'text': 'поддержка OR оператор OR колл-центр',
                'per_page': 10
            }
            
            async with session.get(vac_url, params=params, timeout=10) as vac_response:
                if vac_response.status != 200:
                    return []
                vacancies = await vac_response.json()
                return vacancies.get('items', [])
    except:
        return []

async def gather_company_data(session, company):
    """Собирает все данные по компании (асинхронно)"""
    website_text = await fetch_website(session, company['site'])
    hh_vacancies = await fetch_hh_vacancies(session, company['name'])
    
    return {
        'company': company,
        'website_text': website_text,
        'hh_vacancies': hh_vacancies
    }