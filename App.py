import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd

# 遺忘曲線間隔設定 (天數)
INTERVALS = [1, 2, 4, 7, 15, 30, 60]

# --- 1. 資料庫初始化與操作 ---
def init_db():
    conn = sqlite3.connect('vocab.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE,
            meaning TEXT,
            level INTEGER,
            next_review_date DATE,
            mistake_count INTEGER
        )
    ''')
    conn.commit()
    return conn

def add_word(conn, word, meaning):
    c = conn.cursor()
    today = datetime.now().date()
    try:
        c.execute('''
            INSERT INTO vocab (word, meaning, level, next_review_date, mistake_count)
            VALUES (?, ?, 0, ?, 0)
        ''', (word, meaning, today))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # 單字已存在

def get_due_words(conn):
    c = conn.cursor()
    today = datetime.now().date()
    c.execute('SELECT id, word, meaning, level, mistake_count FROM vocab WHERE next_review_date <= ?', (today,))
    return c.fetchall()

def get_weak_words(conn):
    c = conn.cursor()
    c.execute('SELECT id, word, meaning, level, mistake_count FROM vocab WHERE mistake_count > 0 ORDER BY mistake_count DESC')
    return c.fetchall()

def get_all_words(conn):
    c = conn.cursor()
    c.execute('SELECT id, word, meaning, level, mistake_count FROM vocab ORDER BY id DESC')
    return c.fetchall()

def update_word(conn, word_id, level, remembered, mistake_count):
    c = conn.cursor()
    if remembered:
        new_level = min(level + 1, len(INTERVALS) - 1)
    else:
        new_level = 0 # 忘記了，打回原形
        mistake_count += 1
    
    next_review = datetime.now().date() + timedelta(days=INTERVALS[new_level])
    
    c.execute('''
        UPDATE vocab SET level = ?, next_review_date = ?, mistake_count = ? WHERE id = ?
    ''', (new_level, next_review, mistake_count, word_id))
    conn.commit()

# --- 2. Streamlit UI 介面 ---
st.set_page_config(page_title="遺忘曲線單字 App", page_icon="🧠", layout="centered")

conn = init_db()

st.title("🧠 遺忘曲線單字記憶系統")

# 使用標籤頁切換功能
tab1, tab2, tab3 = st.tabs(["📝 新增單字", "🎯 測驗與練習", "📊 弱點分析"])

# --- 標籤頁 1: 新增單字 ---
with tab1:
    st.header("輸入新單字")
    with st.form("add_word_form"):
        new_word = st.text_input("英文單字")
        new_meaning = st.text_input("中文意思")
        submitted = st.form_submit_button("加入計畫")
        
        if submitted:
            if new_word and new_meaning:
                success = add_word(conn, new_word.strip().lower(), new_meaning.strip())
                if success:
                    st.success(f"已成功加入單字：{new_word}")
                else:
                    st.error("這個單字已經在字庫中囉！")
            else:
                st.warning("請填寫單字與意思。")

# --- 標籤頁 2: 測驗與練習 ---
with tab2:
    st.header("開始練習")
    
    practice_mode = st.radio("選擇練習模式：", 
                               ["📅 每日複習 (依計畫)", "🏋️ 強化弱點 (忘記次數>0)", "🔍 自訂單字練習"], 
                               horizontal=True)
    
    if practice_mode == "📅 每日複習 (依計畫)":
        words_list = get_due_words(conn)
    elif practice_mode == "🏋️ 強化弱點 (忘記次數>0)":
        words_list = get_weak_words(conn)
    else:
        all_words = get_all_words(conn)
        if all_words:
            word_options = {f"{w[1]} ({w[2]})": w for w in all_words}
            selected_key = st.selectbox("請尋找並選擇要練習的單字：", list(word_options.keys()))
            words_list = [word_options[selected_key]]
        else:
            words_list = []

    if 'quiz_state' not in st.session_state:
        st.session_state.quiz_state = 'question'
    if 'current_word_id' not in st.session_state:
        st.session_state.current_word_id = None
    if 'wrong_word_info' not in st.session_state:
        st.session_state.wrong_word_info = None

    if not words_list:
        if st.session_state.quiz_state != 'wrong_feedback':
            st.info("太棒了！目前這個模式下沒有待測驗的單字。🎉")
            st.session_state.quiz_state = 'question'
    else:
        current_word = words_list[0]
        word_id, word, meaning, level, mistakes = current_word
        
        if st.session_state.current_word_id != word_id and st.session_state.quiz_state != 'wrong_feedback':
            st.session_state.quiz_state = 'question'
            st.session_state.current_word_id = word_id

    # 狀態一：顯示題目 (拼字測驗：給中文猜英文)
    if st.session_state.quiz_state == 'question' and words_list:
        if practice_mode != "🔍 自訂單字練習":
            st.write(f"待複習數量：**{len(words_list)}**")
        
        st.markdown(f"<h3 style='text-align: center; color: #555;'>「{meaning}」的正確英文是：</h3>", unsafe_allow_html=True)
        
        user_answer = st.text_input("請輸入英文單字：", key=f"input_{word_id}")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("送出答案", use_container_width=True):
                if user_answer.strip().lower() == word.lower():
                    st.success("🎉 答對了！")
                    update_word(conn, word_id, level, True, mistakes)
                    st.session_state.quiz_state = 'question'
                    st.rerun()
                else:
                    # 答錯：儲存錯誤單字資訊，進入錯題檢討狀態
                    st.session_state.wrong_word_info = {"word": word, "meaning": meaning}
                    update_word(conn, word_id, level, False, mistakes)
                    st.session_state.quiz_state = 'wrong_feedback'
                    st.rerun()
        with col2:
            if st.button("不會，直接看答案", use_container_width=True):
                st.session_state.wrong_word_info = {"word": word, "meaning": meaning}
                update_word(conn, word_id, level, False, mistakes)
                st.session_state.quiz_state = 'wrong_feedback'
                st.rerun()

    # 狀態二：答錯時的回饋檢討畫面 (明確顯示正確英文與中文意思)
    elif st.session_state.quiz_state == 'wrong_feedback':
        st.error("❌ 拼錯了或是忘記囉！請看正確答案並加深記憶：")
        
        if st.session_state.wrong_word_info:
            correct_word = st.session_state.wrong_word_info["word"]
            correct_meaning = st.session_state.wrong_word_info["meaning"]
            
            # 同時顯示正確的英文單字與中文意思
            st.markdown(f"<h2 style='text-align: center; color: #FF4B4B; font-size: 3rem;'>{correct_word}</h2>", unsafe_allow_html=True)
            st.markdown(f"<h4 style='text-align: center; color: #333;'>中文意思：{correct_meaning}</h4>", unsafe_allow_html=True)
        
        if st.button("👉 我記住了，前往下一題", use_container_width=True):
            st.session_state.quiz_state = 'question'
            st.session_state.wrong_word_info = None # 清除暫存
            st.rerun()

# --- 標籤頁 3: 弱點分析 ---
with tab3:
    st.header("你的單字庫與弱點")
    df = pd.read_sql_query("SELECT word AS 單字, meaning AS 意思, next_review_date AS 下次複習日, mistake_count AS 忘記次數 FROM vocab ORDER BY mistake_count DESC", conn)
    
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        st.caption("「忘記次數」越高的單字，代表是你最常忘記的弱點喔！")
    else:
        st.write("目前字庫還是空的。")
