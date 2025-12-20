def decide_support_size_async(features, company):
    """Принимает решение на основе ВСЕХ данных"""
    print(f"    🤔 Анализ {company['name']}: ", end='')
    
    # 1. Уровень A - прямое доказательство
    if features.get('level_a'):
        print(f"Уровень A: {features['level_a']} чел.")
        return {
            'support_team_size_min': features['level_a'],
            'support_evidence': f"Прямое упоминание {features['level_a']} сотрудников поддержки",
            'evidence_url': f"https://{company['site']}",
            'evidence_type': 'site',
            'decision_logic': 'LEVEL_A_DIRECT'
        }
    
    # 2. Уровень B - косвенные признаки
    if features.get('has_24_7'):
        print(f"Уровень B: 24/7 + признаки")
        
        additional = []
        size = 10  # Базовый минимум для круглосуточной работы
        
        # Признаки с сайта
        if features.get('has_shifts'):
            additional.append("сменный график")
            size = max(size, 12)
        
        if len(features.get('found_levels', [])) >= 2:
            levels = ', '.join(sorted(features['found_levels']))
            additional.append(f"уровни {levels}")
            size = max(size, 10 + len(features['found_levels']) * 2)
        
        if features.get('vacancies_count', 0) >= 3:
            additional.append(f"{features['vacancies_count']} вакансий")
            size = max(size, features['vacancies_count'] * 3)
        
        # Дополнительные данные из company_base.json
        if 'clients_millions' in company and company['clients_millions']:
            try:
                clients = float(company['clients_millions'])
                # Расчёт на основе клиентов
                estimated = max(10, int(clients * 0.5 * 1000))  # 0.5 на 1 млн
                additional.append(f"{clients}M клиентов")
                size = max(size, estimated)
            except:
                pass
        
        if additional:
            return {
                'support_team_size_min': size,
                'support_evidence': f"Круглосуточная работа + {' + '.join(additional)}",
                'evidence_url': f"https://{company['site']}",
                'evidence_type': 'site',
                'decision_logic': f'LEVEL_B_24_7_PLUS_{len(additional)}'
            }
    
    # 3. Уровень C - только данные о клиентах
    if 'clients_millions' in company and company['clients_millions']:
        try:
            clients = float(company['clients_millions'])
            if clients >= 0.02:  # Минимум 20,000 клиентов для команды 10+
                calculated_size = max(10, int(clients * 500))  # 1:500 соотношение
                print(f"Уровень C: расчёт от {clients}M клиентов")
                return {
                    'support_team_size_min': calculated_size,
                    'support_evidence': f"Расчёт на основе {clients} млн клиентов (соотношение 1:500)",
                    'evidence_url': f"https://{company['site']}",
                    'evidence_type': 'calculated',
                    'decision_logic': f'LEVEL_C_CALCULATED_{clients}M'
                }
        except:
            pass
    
    print("❌ недостаточно данных")
    return None