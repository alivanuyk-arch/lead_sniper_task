import sys
import time
import json
from datetime import datetime
from src import (
    load_company_base,
    filter_valid_companies,
    parse_website,
    search_hh_vacancies,
    enrich_with_news,  # ← НОВЫЙ ИМПОРТ!
    analyze_company_findings,
    normalize_record,
    save_to_csv
)

def process_company(company, index, total):
    """Обрабатывает одну компанию через все этапы"""
    print(f"\n{'='*60}")
    print(f"[{index}/{total}] 🔍 АНАЛИЗ КОМПАНИИ: {company['name']}")
    print(f"   Сайт: {company.get('site', 'нет')}")
    print(f"   ИНН: {company.get('inn', 'нет')}")
    
    try:
        # ========== 1. ПАРСИНГ САЙТА ==========
        print("   📄 Парсинг сайта компании...", end='')
        website_findings = []
        
        if company.get('site'):
            website_findings = parse_website(company['site'], max_pages=3)
            print(f"✅ {len(website_findings)} находок")
        else:
            print("➖ (нет сайта)")
        
        # ========== 2. ПАРСИНГ ВАКАНСИЙ HH ==========
        print("   💼 Поиск вакансий на HH...", end='')
        hh_vacancies = search_hh_vacancies(company['name'])
        print(f"✅ {len(hh_vacancies)} вакансий")
        
        # ========== 3. ПАРСИНГ НОВОСТЕЙ CNEWS ==========
        print("   📰 Поиск в новостях CNews...", end='')
        cnews_start = time.time()
        
        try:
            # Используем новую функцию обогащения CNews
            all_findings = enrich_with_news(company['name'], website_findings)
            
            # Отдельно считаем находки CNews
            cnews_findings = [f for f in all_findings if f.get('source') == 'cnews']
            cnews_time = time.time() - cnews_start
            
            print(f"✅ {len(cnews_findings)} находок ({cnews_time:.1f}с)")
            
            if cnews_findings:
                print("     Находки CNews:")
                for finding in cnews_findings[:3]:  # Показываем первые 3
                    print(f"       • {finding.get('value', '?')}+ чел: {finding.get('text', '')[:80]}...")
        
        except ImportError as e:
            print("➖ (модуль не подключен)")
            all_findings = website_findings
        except Exception as e:
            print(f"⚠️ Ошибка: {str(e)[:50]}")
            all_findings = website_findings
        
        # ========== 4. АНАЛИЗ И ПРИНЯТИЕ РЕШЕНИЙ ==========
        print("   🧠 Анализ доказательств...", end='')
        
        # Передаем как общий массив находок
        decision = analyze_company_findings(all_findings, hh_vacancies, company)
        
        if decision:
            print(f"✅ Решение принято: {decision.get('support_team_size_min', 0)}+ чел")
            
            # Собираем полную запись
            record = {
                'inn': company.get('inn', ''),
                'name': company.get('name', ''),
                'site': company.get('site', ''),
                'category': company.get('category', ''),
                'support_team_size_min': decision.get('support_team_size_min', 0),
                'support_evidence': decision.get('support_evidence', ''),
                'evidence_url': decision.get('evidence_url', ''),
                'evidence_type': decision.get('evidence_type', ''),
                'decision_logic': decision.get('decision_logic', ''),
                'has_cnews_evidence': len(cnews_findings) > 0 if 'cnews_findings' in locals() else False,
                'cnews_findings_count': len(cnews_findings) if 'cnews_findings' in locals() else 0,
                'processing_timestamp': datetime.now().isoformat()
            }
            
            # Добавляем булевы признаки из находок сайта
            from src.merge_normalize import (
                check_support_email, check_contact_form, check_online_chat,
                check_messengers, check_support_section, check_kb_faq
            )
            
            record.update({
                'has_support_email': check_support_email(website_findings),
                'has_contact_form': check_contact_form(website_findings),
                'has_online_chat': check_online_chat(website_findings),
                'has_messengers': check_messengers(website_findings),
                'has_support_section': check_support_section(website_findings),
                'has_kb_or_faq': check_kb_faq(website_findings),
                'mentions_24_7': any(f['type'] == '24_7' for f in website_findings)
            })
            
            # Нормализуем запись
            record = normalize_record(record)
            return record
            
        else:
            print("➖ Недостаточно доказательств")
            return None
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Основная функция"""
    print("🚀 LEAD SNIPER TASK - ЗАПУСК")
    print("=" * 60)
    
    # Загружаем компании
    companies = load_company_base('data/company_base.json')
    valid_companies = filter_valid_companies(companies)
    
    print(f"📊 Всего компаний: {len(companies)}")
    print(f"✅ Валидных компаний: {len(valid_companies)}")
    
    if not valid_companies:
        print("❌ Нет компаний для обработки")
        return
    
    # Обрабатываем компании
    results = []
    
    for i, company in enumerate(valid_companies, 1):
        print(f"\n📋 Обработка компаний {i}/{len(valid_companies)}")
        
        result = process_company(company, i, len(valid_companies))
        
        if result:
            results.append(result)
            print(f"   ✅ Добавлено в результаты")
        else:
            print(f"   ➖ Пропущено")
        
        # Пауза между компаниями (особенно если был CNews)
        if i < len(valid_companies):
            pause_time = 5 if len(results) > 0 and results[-1].get('has_cnews_evidence') else 2
            print(f"   ⏸️  Пауза {pause_time} секунд...")
            time.sleep(pause_time)
    
    # Сохраняем результаты
    if results:
        print(f"\n💾 Сохранение {len(results)} результатов...")
        
        filename = save_to_csv(results, 'data/companies.csv')
        print(f"✅ Результаты сохранены в: {filename}")
        
        # Дополнительный вывод статистики
        with_cnews = sum(1 for r in results if r.get('has_cnews_evidence'))
        avg_cnews = sum(r.get('cnews_findings_count', 0) for r in results) / max(len(results), 1)
        
        print(f"\n📈 СТАТИСТИКА С CNEWS:")
        print(f"   • Компаний с доказательствами CNews: {with_cnews}/{len(results)}")
        print(f"   • Среднее находок CNews на компанию: {avg_cnews:.1f}")
        print(f"   • Макс. размер команды: {max(r.get('support_team_size_min', 0) for r in results)}")
        
    else:
        print("❌ Не удалось собрать ни одного результата")

if __name__ == "__main__":
    main()