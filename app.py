import streamlit as st
import pandas as pd
import sqlite3
import time
import hashlib
import secrets
import re
import concurrent.futures
from datetime import datetime
from yookassa import Configuration, Payment
from core import LeadForgeCore
from google import genai

st.set_page_config(
    page_title="LeadForge",
    page_icon="⚡",
    layout="wide"
)

# --- ИНИЦИАЛИЗАЦИЯ GEMINI AI ---
ai_client = None
ai_available = False
try:
    if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
        ai_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        ai_available = True
except Exception:
    ai_available = False

# --- СТИЛИЗАЦИЯ (МИНИМАЛИЗМ & НЕОН) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    
    @keyframes backgroundShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    @keyframes borderGlow {
        0% { border-color: rgba(16, 185, 129, 0.2); box-shadow: 0 0 15px rgba(16, 185, 129, 0.05); }
        50% { border-color: rgba(16, 185, 129, 0.5); box-shadow: 0 0 30px rgba(16, 185, 129, 0.2); }
        100% { border-color: rgba(16, 185, 129, 0.2); box-shadow: 0 0 15px rgba(16, 185, 129, 0.05); }
    }

    @keyframes tabFadeIn {
        from { opacity: 0; transform: translateY(8px) scale(0.99); }
        to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .stApp {
        background: linear-gradient(-45deg, #020617, #061513, #020617, #0b1329);
        background-size: 400% 400%;
        animation: backgroundShift 15s ease infinite;
        color: #f8fafc;
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    #MainMenu, footer, header {visibility: hidden;}

    div.block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
        animation: tabFadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    .stTabs [data-baseweb="tab-panel"] {
        animation: tabFadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    .glass-card {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.85) 0%, rgba(2, 6, 23, 0.95) 100%);
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 26px;
        border-radius: 20px;
        backdrop-filter: blur(24px);
        animation: borderGlow 6s infinite ease-in-out;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        margin-bottom: 20px;
    }

    .top-bar {
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 14px 24px;
        border-radius: 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
        backdrop-filter: blur(16px);
        box-shadow: 0 10px 30px rgba(0,0,0,0.4);
    }

    .stButton>button {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
        font-weight: 700;
        border-radius: 12px;
        border: none;
        height: 46px;
        width: 100%;
        box-shadow: 0 4px 20px rgba(16, 185, 129, 0.3);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 0 25px rgba(16, 185, 129, 0.7);
        background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
    }

    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        background-color: rgba(2, 6, 23, 0.9) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 12px !important;
        padding: 12px !important;
    }
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: #10b981 !important;
        box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.3) !important;
    }

    .pricing-card {
        background: linear-gradient(180deg, rgba(15, 23, 42, 0.9) 0%, rgba(2, 6, 23, 0.95) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 35px 25px;
        border-radius: 20px;
        text-align: center;
        box-shadow: 0 20px 40px rgba(0,0,0,0.5);
        transition: transform 0.3s ease, border-color 0.3s ease;
    }
    .pricing-card:hover {
        transform: translateY(-4px);
        border-color: rgba(52, 211, 153, 0.6);
    }
    </style>
""", unsafe_allow_html=True)

# --- НАСТРОЙКА ЮКААССЫ ИЗ SECRETS ---
yookassa_configured = False
try:
    if "YOOKASSA_SHOP_ID" in st.secrets and "YOOKASSA_SECRET_KEY" in st.secrets:
        Configuration.account_id = st.secrets["YOOKASSA_SHOP_ID"]
        Configuration.secret_key = st.secrets["YOOKASSA_SECRET_KEY"]
        yookassa_configured = True
except Exception:
    yookassa_configured = False

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def process_spintax(text):
    def replace_match(match):
        options = match.group(1).split('|')
        import random
        return random.choice(options)
    pattern = re.compile(r'\{([^}]+)\}')
    return pattern.sub(replace_match, text)

def is_valid_email(email):
    if not isinstance(email, str):
        return False
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return bool(re.match(pattern, email.strip()))

def generate_ai_offer_and_triggers(niche, city):
    fallback_offer = "{Здравствуйте|Добрый день|Приветствую}, {команда|коллеги|} {company_name}! Предлагаем услуги по направлению " + niche + " в городе {city}."
    fallback_triggers = f"{niche}, заказать {niche}, услуги {niche}, студия {niche}, {niche} в городе {city}"
    
    if not ai_available:
        return fallback_offer, fallback_triggers
    
    def _call_gemini():
        prompt = f"""
        Напиши холодное коммерческое предложение для рассылки в нише "{niche}" для города "{city}".
        Используй Spintax-вариации через вертикальную черту в фигурных скобках (например, {{Привет|Здравствуйте}}).
        Используй теги подстановки {{company_name}} и {{city}}.
        Вторым пунктом через запятую сгенерируй 15-20 поисковых триггеров.
        
        Формат строго:
        ---OFFER---
        [Текст]
        ---TRIGGERS---
        [Триггеры через запятую]
        """
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_call_gemini)
        try:
            result_text = future.result(timeout=6)
            if "---OFFER---" in result_text and "---TRIGGERS---" in result_text:
                parts = result_text.split("---TRIGГERS---") if "---TRIGГERS---" in result_text else result_text.split("---TRIGGERS---")
                return parts[0].replace("---OFFER---", "").strip(), parts[1].strip()
            else:
                return result_text, fallback_triggers
        except Exception:
            return fallback_offer, fallback_triggers

def init_db():
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY)")
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = [col[1].lower() for col in cursor.fetchall()]
    
    columns_to_check = {
        "password": "TEXT", "email": "TEXT", "tier": "TEXT DEFAULT 'free'",
        "sent_today": "INTEGER DEFAULT 0", "last_reset_date": "TEXT",
        "is_verified": "INTEGER DEFAULT 1", "is_blocked": "INTEGER DEFAULT 0", "reset_token": "TEXT"
    }
    for col_name, col_type in columns_to_check.items():
        if col_name.lower() not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT, 
            channel TEXT, 
            email TEXT, 
            status TEXT,
            UNIQUE(username, email)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tier_limits (tier TEXT PRIMARY KEY, daily_limit INTEGER)
    """)
    cursor.execute("INSERT OR IGNORE INTO tier_limits (tier, daily_limit) VALUES ('free', 3)")
    cursor.execute("INSERT OR IGNORE INTO tier_limits (tier, daily_limit) VALUES ('monthly', 50)")
    cursor.execute("INSERT OR IGNORE INTO tier_limits (tier, daily_limit) VALUES ('lifetime', 999999)")
    conn.commit()
    conn.close()

init_db()

def get_limit_for_tier(tier):
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT daily_limit FROM tier_limits WHERE tier = ?", (tier,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 3

def register_user(username, password, email):
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return False, "Пользователь уже существует"
    today_str = datetime.now().strftime("%Y-%m-%d")
    hashed_pw = hash_password(password)
    cursor.execute("INSERT INTO users (username, password, email, tier, sent_today, last_reset_date, is_verified, is_blocked) VALUES (?, ?, ?, ?, ?, ?, 1, 0)", (username, hashed_pw, email, "free", 0, today_str))
    conn.commit()
    conn.close()
    return True, "Успешно"

def get_user_info(username):
    if username == "admin":
        return "admin", 0
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT tier, sent_today, last_reset_date FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not row:
        tier, sent_today = "free", 0
    else:
        tier, sent_today, last_reset_date = row
        if last_reset_date != today_str:
            sent_today = 0
            cursor.execute("UPDATE users SET sent_today = 0, last_reset_date = ? WHERE username = ?", (today_str, username))
            conn.commit()
    conn.close()
    return tier, sent_today

def update_user_tier(username, new_tier):
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tier = ? WHERE username = ?", (new_tier, username))
    conn.commit()
    conn.close()

def increment_sent_count(username):
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET sent_today = sent_today + 1 WHERE username = ?", (username,))
    conn.commit()
    conn.close()

def load_leads_from_db(username):
    conn = sqlite3.connect("saas_database.db")
    df = pd.read_sql("SELECT channel AS 'Компания', email AS 'Email', status AS 'Статус' FROM user_leads WHERE username = ?", conn, params=(username,))
    conn.close()
    if df.empty:
        df = pd.DataFrame([{"Компания": "Пример", "Email": "client@example.com", "Статус": "В очереди"}])
    return df

def save_leads_to_db(username, df):
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    for _, row in df.iterrows():
        email_val = str(row.get("Email", "")).strip()
        if not is_valid_email(email_val):
            continue
        cursor.execute("""
            INSERT OR IGNORE INTO user_leads (username, channel, email, status) 
            VALUES (?, ?, ?, ?)
        """, (username, str(row.get("Компания", "")), email_val, str(row.get("Статус", "В очереди"))))
    conn.commit()
    conn.close()

def remove_user_duplicates(username):
    conn = sqlite3.connect("saas_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM user_leads 
        WHERE username = ? AND id NOT IN (
            SELECT MIN(id) 
            FROM user_leads 
            WHERE username = ?
            GROUP BY email
        )
    """, (username, username))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count

# --- СЕССИЯ ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "ai_template" not in st.session_state:
    init_off, init_trig = generate_ai_offer_and_triggers("3D визуализация", "Новочеркасск")
    st.session_state.ai_template = init_off
    st.session_state.auto_keywords = init_trig
if "stop_process" not in st.session_state:
    st.session_state.stop_process = False

query_params = st.query_params
if "reset_token" in query_params:
    token = query_params["reset_token"]
    st.markdown("<h2 style='text-align: center;'>Сброс пароля</h2>", unsafe_allow_html=True)
    with st.form("new_password_form"):
        new_p1 = st.text_input("Новый пароль", type="password")
        new_p2 = st.text_input("Подтвердите пароль", type="password")
        if st.form_submit_button("Сохранить"):
            if new_p1 and new_p1 == new_p2:
                conn = sqlite3.connect("saas_database.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password = ?, reset_token = NULL WHERE reset_token = ?", (hash_password(new_p1), token))
                conn.commit()
                conn.close()
                st.success("Пароль изменен")
                st.query_params.clear()
                time.sleep(1.5)
                st.rerun()
            else:
                st.error("Пароли не совпадают")
    st.stop()

# Обработка успешного возврата после оплаты ЮKassa
if "success" in query_params and query_params["success"] == "true":
    target_tier = query_params.get("tier", "monthly")
    if st.session_state.authenticated:
        update_user_tier(st.session_state.username, target_tier)
        st.success("🎉 Оплата прошла успешно! Тариф обновлен.")
        st.query_params.clear()
        time.sleep(1.5)
        st.rerun()

# --- АВТОРИЗАЦИЯ ---
if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align: center; margin-top: 30px; font-weight: 800; background: linear-gradient(135deg, #34d399, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>LeadForge</h1>", unsafe_allow_html=True)
    
    _, col_center, _ = st.columns([1, 1.2, 1])
    with col_center:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        auth_mode = st.radio("Режим", ["Вход", "Регистрация", "Сброс"], horizontal=True, label_visibility="collapsed")
        st.divider()
        
        if auth_mode == "Вход":
            with st.form("login_form"):
                l_user = st.text_input("Логин")
                l_pass = st.text_input("Пароль", type="password")
                if st.form_submit_button("Войти"):
                    admin_secret = st.secrets.get("ADMIN_PASSWORD", "admin123")
                    if l_user == "admin" and l_pass == admin_secret:
                        st.session_state.authenticated = True
                        st.session_state.username = "admin"
                        st.rerun()
                    conn = sqlite3.connect("saas_database.db")
                    cursor = conn.cursor()
                    cursor.execute("SELECT password, is_blocked FROM users WHERE username = ?", (l_user,))
                    row = cursor.fetchone()
                    conn.close()
                    if row and row[0] == hash_password(l_pass):
                        if row[1] == 1:
                            st.error("Аккаунт заблокирован")
                        else:
                            st.session_state.authenticated = True
                            st.session_state.username = l_user
                            st.session_state.leads_df = load_leads_from_db(l_user)
                            st.rerun()
                    else:
                        st.error("Неверный логин или пароль")
                        
        elif auth_mode == "Регистрация":
            with st.form("registration_form"):
                r_user = st.text_input("Логин")
                r_pass = st.text_input("Пароль", type="password")
                r_email = st.text_input("Email")
                if st.form_submit_button("Создать аккаунт"):
                    if r_user and r_pass and r_email:
                        success, msg = register_user(r_user, r_pass, r_email)
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.username = r_user
                            st.session_state.leads_df = load_leads_from_db(r_user)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Заполните поля")
                        
        elif auth_mode == "Сброс":
            with st.form("forgot_form"):
                f_email = st.text_input("Email для восстановления")
                if st.form_submit_button("Отправить"):
                    if f_email:
                        conn = sqlite3.connect("saas_database.db")
                        cursor = conn.cursor()
                        cursor.execute("SELECT username FROM users WHERE email = ?", (f_email,))
                        res = cursor.fetchone()
                        conn.close()
                        if res:
                            token = secrets.token_urlsafe(32)
                            conn = sqlite3.connect("saas_database.db")
                            cursor = conn.cursor()
                            cursor.execute("UPDATE users SET reset_token = ? WHERE email = ?", (token, f_email))
                            conn.commit()
                            conn.close()
                            st.success(f"Ссылка: ?reset_token={token}")
                        else:
                            st.error("Email не найден")
                    else:
                        st.warning("Введите email")
                        
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# --- ШАПКА С ИНДИКАТОРОМ ЛИМИТОВ ---
username = st.session_state.username
tier, sent_today = get_user_info(username)
daily_limit = get_limit_for_tier(tier)

brand_name = "LeadForge ULTRA" if tier == "lifetime" else ("LeadForge PRO" if tier == "monthly" else "LeadForge")
tier_display = {"free": "Free", "monthly": "PRO", "lifetime": "ULTRA"}.get(tier, tier.upper())

remaining_leads = max(0, daily_limit - sent_today) if daily_limit != 999999 else "Безлимит"
progress_val = min(1.0, sent_today / daily_limit) if daily_limit != 999999 else 0.0

st.markdown(f"""
    <div class="top-bar">
        <div><b>{brand_name}</b> <span style="color: #34d399; margin-left: 8px;">● {username}</span></div>
        <div style="color: #94a3b8; font-size: 0.9rem;">
            Тариф: <span style="color: #f8fafc; font-weight: 600;">{tier_display}</span> &nbsp;|&nbsp; 
            Осталось лидов сегодня: <span style="color: #34d399; font-weight: 600;">{remaining_leads}</span> (Отправлено: {sent_today}/{daily_limit if daily_limit != 999999 else '∞'})
        </div>
    </div>
""", unsafe_allow_html=True)

if daily_limit != 999999:
    st.progress(progress_val, text=f"Лимит рассылки на сегодня: использовано {sent_today} из {daily_limit} писем")

_, logout_col = st.columns([10, 1])
with logout_col:
    if st.button("Выйти"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.rerun()

# --- SMTP НАСТРОЙКИ ---
with st.expander("Настройка SMTP (Яндекс)", expanded=False):
    st.markdown("""
        **Как получить пароль приложения Яндекс:**
        1. Перейдите в ваш **Яндекс ID** (id.yandex.ru) → раздел **Безопасность**.
        2. Выберите пункт **Пароли приложений**.
        3. Создайте новый пароль для **Почты** и вставьте его в поле справа.
    """)
    s_col1, s_col2 = st.columns(2)
    with s_col1:
        yandex_email = st.text_input("Почта", value="denisastak@yandex.ru")
    with s_col2:
        yandex_pass = st.text_input("Пароль приложения", type="password")

# --- АДМИН ПАНЕЛЬ ---
if username == "admin":
    st.markdown("## Административная панель")
    conn = sqlite3.connect("saas_database.db")
    users_df = pd.read_sql("SELECT username, email, tier, sent_today, is_blocked FROM users", conn)
    limits_df = pd.read_sql("SELECT tier AS 'Тариф', daily_limit AS 'Лимит' FROM tier_limits", conn)
    conn.close()
    
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    for _, u_row in users_df.iterrows():
        u_name, u_email, u_tier, u_blocked = u_row['username'], u_row['email'] or "-", u_row['tier'], bool(u_row['is_blocked'])
        uc1, uc2, uc3, uc4, uc5 = st.columns([1.5, 1.2, 0.9, 0.9, 0.9])
        with uc1: st.markdown(f"**{u_name}**<br><span style='color:#94a3b8;font-size:0.8rem;'>{u_email}</span>", unsafe_allow_html=True)
        with uc2: new_t = st.selectbox("Тариф", ["free", "monthly", "lifetime"], index=["free", "monthly", "lifetime"].index(u_tier) if u_tier in ["free", "monthly", "lifetime"] else 0, key=f"t_{u_name}")
        with uc3: is_bl = st.checkbox("Блок", value=u_blocked, key=f"b_{u_name}")
        with uc4:
            if st.button("Сохр", key=f"s_{u_name}"):
                conn = sqlite3.connect("saas_database.db")
                cur = conn.cursor()
                cur.execute("UPDATE users SET tier = ?, is_blocked = ? WHERE username = ?", (new_t, 1 if is_bl else 0, u_name))
                conn.commit()
                conn.close()
                st.rerun()
        with uc5:
            if u_name != "admin":
                if st.button("Удалить", key=f"d_{u_name}"):
                    conn = sqlite3.connect("saas_database.db")
                    cur = conn.cursor()
                    cur.execute("DELETE FROM users WHERE username = ?", (u_name,))
                    cur.execute("DELETE FROM user_leads WHERE username = ?", (u_name,))
                    conn.commit()
                    conn.close()
                    st.rerun()
        st.divider()
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# --- ВКЛАДКИ ---
tab_send, tab_sources, tab_crm, tab_analytics, tab_tariffs, tab_settings, tab_support = st.tabs([
    "Кампания", 
    "Источники", 
    "База лидов", 
    "Аналитика", 
    "Тарифы", 
    "Триггеры",
    "Поддержка"
])

with tab_send:
    col_left, col_right = st.columns([1.1, 0.9], gap="large")
    with col_left:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("### Конструктор")
        with st.expander("Генератор (AI)", expanded=True):
            s_col_a, s_col_b = st.columns(2)
            with s_col_a:
                ai_niche = st.text_input("Ниша", value="3D визуализация")
            with s_col_b:
                ai_city = st.text_input("Город", value="Новочеркасск")
                
            if st.button("Сгенерировать"):
                with st.spinner("Генерация..."):
                    new_offer, new_triggers = generate_ai_offer_and_triggers(ai_niche, ai_city)
                    st.session_state.ai_template = new_offer
                    st.session_state.auto_keywords = new_triggers
                    st.success("Готово")
                    time.sleep(0.3)
                    st.rerun()

        subject = st.text_input("Тема", value="Предложение по сотрудничеству")
        email_body = st.text_area("Текст", value=st.session_state.ai_template, height=190)
        
        attach_mode = st.radio("Файл", ["Нет", "PDF / DOCX"], horizontal=True)
        file_bytes, file_name = None, None
        if attach_mode == "PDF / DOCX":
            up_file = st.file_uploader("Загрузить", type=["pdf", "docx"])
            if up_file:
                file_bytes, file_name = up_file.read(), up_file.name

        b_col1, b_col2 = st.columns(2)
        with b_col1:
            btn_start = st.button("Запуск")
        with b_col2:
            btn_stop = st.button("Стоп")
        
        if btn_stop:
            st.session_state.stop_process = True
        st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("### Терминал")
        if "logs" not in st.session_state:
            st.session_state.logs = ">>> Готов к работе.\n"
        log_box = st.empty()
        log_box.text_area("Logs", value=st.session_state.logs, height=450, disabled=True)

        def add_log(msg):
            st.session_state.logs += f"[{time.strftime('%H:%M:%S')}] {msg}\n"
            log_box.text_area("Logs", value=st.session_state.logs, height=450, disabled=True)

        if btn_start:
            st.session_state.stop_process = False
            curr_tier, sent_today = get_user_info(username)
            limit = get_limit_for_tier(curr_tier)
            if sent_today >= limit:
                st.error("Лимит писем на сегодня исчерпан!")
            elif not yandex_email or not yandex_pass:
                st.error("Заполните SMTP настройки")
            else:
                core = LeadForgeCore(yandex_email, yandex_pass)
                for idx, row in st.session_state.leads_df.iterrows():
                    if st.session_state.stop_process:
                        add_log("Остановлено.")
                        break
                    _, cur_sent = get_user_info(username)
                    if cur_sent >= limit:
                        add_log("Достигнут дневной лимит.")
                        break
                    email, status, comp_name = str(row.get("Email", "")), str(row.get("Статус", "")), str(row.get("Компания", "партнер"))
                    if "@" not in email:
                        continue
                    if status in ["В очереди", "Ошибка"]:
                        add_log(f"Отправка: {email}...")
                        raw_body = email_body.replace("{company_name}", comp_name).replace("{city}", ai_city)
                        formatted_body = process_spintax(raw_body)
                        success = core.send_email_from_web(to_email=email, subject=subject, body_text=formatted_body, file_bytes=file_bytes, file_name=file_name, log_callback=add_log)
                        st.session_state.leads_df.at[idx, "Статус"] = "Отправлено" if success else "Ошибка"
                        save_leads_to_db(username, st.session_state.leads_df)
                        if success:
                            increment_sent_count(username)
                        time.sleep(2)
        st.markdown('</div>', unsafe_allow_html=True)

with tab_sources:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### Источники")
    sc1, sc2 = st.columns(2)
    with sc1:
        st.checkbox("YouTube", value=True)
        st.checkbox("Поисковики", value=True)
        st.checkbox("2ГИС / Карты", value=True)
        st.checkbox("Авито / Юла", value=True)
    with sc2:
        st.checkbox("Behance", value=False)
        st.checkbox("VC.ru / Habr", value=False)
        st.checkbox("VK Сообщества", value=True)
        st.checkbox("Telegram", value=True)
    st.markdown('</div>', unsafe_allow_html=True)

with tab_crm:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### База лидов")
    
    if st.button("Удалить дубликаты"):
        deleted = remove_user_duplicates(username)
        st.session_state.leads_df = load_leads_from_db(username)
        st.success(f"Удалено: {deleted}")
        time.sleep(1)
        st.rerun()

    up_leads = st.file_uploader("Импорт CSV / XLSX", type=["csv", "xlsx"])
    if up_leads:
        try:
            df_new = pd.read_csv(up_leads) if up_leads.name.endswith('.csv') else pd.read_excel(up_leads)
            if 'Компания' in df_new.columns or 'Канал' in df_new.columns and 'Email' in df_new.columns:
                if 'Канал' in df_new.columns and 'Компания' not in df_new.columns:
                    df_new = df_new.rename(columns={'Канал': 'Компания'})
                df_new['Email'] = df_new['Email'].astype(str).str.strip()
                df_new = df_new[df_new['Email'].apply(is_valid_email)]
                if 'Статус' not in df_new.columns:
                    df_new['Статус'] = 'В очереди'
                st.session_state.leads_df = df_new[['Компания', 'Email', 'Статус']]
                save_leads_to_db(username, st.session_state.leads_df)
                st.rerun()
        except Exception:
            pass

    st.divider()
    edited_df = st.data_editor(st.session_state.leads_df, num_rows="dynamic", use_container_width=True, hide_index=True, height=330)
    st.session_state.leads_df = edited_df
    save_leads_to_db(username, st.session_state.leads_df)
    st.download_button("Экспорт CSV", st.session_state.leads_df.to_csv(index=False).encode('utf-8'), f"leads_{username}.csv", "text/csv")
    st.markdown('</div>', unsafe_allow_html=True)

with tab_analytics:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### Аналитика")
    df_l = st.session_state.leads_df
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Всего", len(df_l))
    m2.metric("Отправлено", len(df_l[df_l['Статус'] == 'Отправлено']) if 'Статус' in df_l.columns else 0)
    m3.metric("Просмотрено", len(df_l[df_l['Статус'] == 'Просмотрено']) if 'Статус' in df_l.columns else 0)
    m4.metric("Кликнули", len(df_l[df_l['Статус'] == 'Кликнул']) if 'Статус' in df_l.columns else 0)
    st.divider()
    if not df_l.empty and 'Статус' in df_l.columns:
        st.bar_chart(df_l['Статус'].value_counts())
    st.markdown('</div>', unsafe_allow_html=True)

with tab_tariffs:
    st.markdown("### Тарифы")
    t1, t2, t3 = st.columns(3)
    with t1:
        st.markdown(f'''
            <div class="pricing-card">
                <h3>LeadForge</h3>
                <p style="color:#94a3b8;margin-bottom:15px;">Free</p>
                <div style="font-size:1.6rem;font-weight:700;color:#34d399;">{get_limit_for_tier("free")} / день</div>
            </div>
        ''', unsafe_allow_html=True)
    with t2:
        st.markdown(f'''
            <div class="pricing-card" style="border: 1px solid rgba(52, 211, 153, 0.4);">
                <h3>PRO</h3>
                <p style="color:#94a3b8;margin-bottom:15px;">Monthly</p>
                <div style="font-size:1.6rem;font-weight:700;color:#34d399;">990 ₽</div>
            </div>
        ''', unsafe_allow_html=True)
        if st.button("Купить PRO"):
            if yookassa_configured:
                try:
                    p = Payment.create({
                        "amount": {"value": "990.00", "currency": "RUB"},
                        "confirmation": {"type": "redirect", "return_url": "https://leadforge-app.streamlit.app/?success=true&tier=monthly"},
                        "capture": True, "description": f"PRO подписка для {username}"
                    })
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={p.confirmation.confirmation_url}">', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Ошибка создания платежа ЮKassa: {e}")
            else:
                update_user_tier(username, "monthly")
                st.success("Тестовый режим: Тариф PRO активирован!")
                time.sleep(1)
                st.rerun()
    with t3:
        st.markdown(f'''
            <div class="pricing-card">
                <h3>ULTRA</h3>
                <p style="color:#94a3b8;margin-bottom:15px;">Lifetime</p>
                <div style="font-size:1.6rem;font-weight:700;color:#34d399;">4990 ₽</div>
            </div>
        ''', unsafe_allow_html=True)
        if st.button("Купить ULTRA"):
            if yookassa_configured:
                try:
                    p = Payment.create({
                        "amount": {"value": "4990.00", "currency": "RUB"},
                        "confirmation": {"type": "redirect", "return_url": "https://leadforge-app.streamlit.app/?success=true&tier=lifetime"},
                        "capture": True, "description": f"ULTRA подписка для {username}"
                    })
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={p.confirmation.confirmation_url}">', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Ошибка создания платежа ЮKassa: {e}")
            else:
                update_user_tier(username, "lifetime")
                st.success("Тестовый режим: Тариф ULTRA активирован!")
                time.sleep(1)
                st.rerun()

with tab_settings:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### Авто-генератор триггеров")
    st.text_area("Ключевые слова / триггеры для поиска", value=st.session_state.auto_keywords, height=150)
    st.markdown('</div>', unsafe_allow_html=True)

with tab_support:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### Поддержка, контакты и реквизиты")
    st.write("Если у вас возникли вопросы по работе сервиса, оплате или тарифам, вы всегда можете связаться со службой поддержки.")
    
    st.markdown("---")
    st.markdown("### 📋 Юридическая информация и реквизиты")
    st.markdown("**Статус:** Самозанятый (НПД)")
    st.markdown("**ФИО:** Астахов Денис Юрьевич")
    st.markdown("**ИНН:** `614907689520`")
    st.markdown("**Email поддержки:** denis.astakhov.3d@mail.ru")
    
    st.markdown("---")
    st.markdown("### 📄 Публичная оферта и условия оказания услуг")
    st.markdown("""
    Оплата подписки на программное обеспечение LeadForge означает полное и безоговорочное принятие условий настоящей оферты.
    * **Предмет соглашения:** Предоставление доступа к SaaS-платформе для автоматизированного поиска лидов и отправки email-сообщений.
    * **Порядок активации:** Доступ к выбранному тарифному плану предоставляется автоматически сразу после подтверждения успешной оплаты.
    * **Порядок возврата:** Возврат денежных средств осуществляется в строгом соответствии с действующим законодательством РФ на основании письменного обращения пользователя на email поддержки: **denis.astakhov.3d@mail.ru**.
    """)
    st.markdown('</div>', unsafe_allow_html=True)