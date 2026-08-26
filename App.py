import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import random

# 遺忘曲線間隔設定 (0代表今天重測，接著是1天、2天...)
INTERVALS = [0, 1, 2, 4, 7, 15, 30, 60]

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
    try:
        c.execute("ALTER TABLE vocab ADD COLUMN last_mistake_date DATE")
    except sqlite3.OperationalError:
        pass 
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
        return False

def get_due_words(conn):
    c = conn.cursor()
    today = datetime.now().date()
    c.execute('SELECT id, word, meaning, level, mistake_count FROM vocab WHERE next_review_date <= ?', (today,))
    return c.fetchall()

def update_word(conn, word_id, level, remembered, mistake_count):
    c = conn.cursor()
    today = datetime.now().date()
    
    if remembered:
        new_level = min(level + 1, len(INTERVALS) - 1)
        next_review = today + timedelta(days=INTERVALS[new_level])
        c.execute('UPDATE vocab SET level = ?, next_review_date = ? WHERE id = ?', 
                  (new_level, next_review, word_id))
    else:
        new_level = 0 # 忘記了，間隔歸零（今天繼續測驗）
        mistake_count += 1
        next_review = today + timedelta(days=INTERVALS[new_level])
        c.execute('UPDATE vocab SET level = ?, next_review_date = ?, mistake_count = ?, last_mistake_date = ? WHERE id = ?', 
                  (new_level, next_review, mistake_count, today, word_id))
    conn.commit()

# --- 輔助功能：產生填空字串 ---
def generate_masked_word(word):
    if len(word) <= 2:
        return " _ " * len(word)
    word_list = list(word)
    hide_count = max(1, len(word) // 2) # 隱藏一半的字母
    # 盡量保留第一個字母，隨機挖空其他字母
    available_indices = list(range(1, len(word)))
    if not available_indices:
        available_indices = [0]
    hide_indices = random.sample(available_indices, min(hide_count, len(available_indices)))
    
    for i in hide_indices:
        if word_list[i].isalpha():
            word_list[i] = "_"
    return " ".join(word_list)

# --- 2. Streamlit UI 介面 ---
st.set_page_config(page_title="遺忘曲線單字 App", page_icon="🧠", layout="centered")

conn = init_db()
st.title("🧠 遺忘曲線單字記憶系統")

tab1, tab2, tab3 = st.tabs(["📝 新增單字", "🎯 今日測驗", "📊 弱點分析"])

# --- 標籤頁 1: 新增單字 ---
with tab1:
    st.header("新增單字庫")
    st.subheader("🔹 批量加入")
    bulk_input = st.text_area("格式：英文,中文 (每行一個)", placeholder="apple,蘋果\nbanana,香蕉", height=120)
    if st.button("🚀 批量加入計畫"):
        if bulk_input.strip():
            success_count, fail_count = 0, 0
            for line in bulk_input.strip().split('\n'):
                delimiter = ',' if ',' in line else '，'
                parts = line.split(delimiter)
                if len(parts) >= 2:
                    if add_word(conn, parts[0].strip().lower(), parts[1].strip()):
                        success_count += 1
                    else:
                        fail_count += 1
            st.success(f"成功加入 {success_count} 個單字，{fail_count} 個單字已存在。")

    st.subheader("🔹 單筆輸入")
    with st.form("add_word_form"):
        new_word = st.text_input("英文單字")
        new_meaning = st.text_input("中文意思")
        if st.form_submit_button("單筆加入"):
            if new_word and new_meaning:
                if add_word(conn, new_word.strip().lower(), new_meaning.strip()):
                    st.success(f"已加入：{new_word}")
                else:
                    st.error("單字已在字庫中！")

# --- 標籤頁 2: 今日測驗 ---
with tab2:
    st.header("今日需複習單字")
    due_words = get_due_words(conn)
    
    # 初始化測驗狀態
    if 'quiz_state' not in st.session_state:
        st.session_state.quiz_state = "question"
    
    if not due_words:
        st.info("太棒了！今天的任務全數完成囉！🎉")
        st.session_state.quiz_state = "question" # 重置狀態
    else:
        st.write(f"還有 **{len(due_words)}** 個單字待測驗")
        
        current_word = due_words[0]
        word_id, word, meaning, level, mistakes = current_word
        
        # 狀態一：正在作答
        if st.session_state.quiz_state == "question":
            st.markdown(f"<h4 style='text-align: center; color: #666;'>請問這個中文的英文是什麼？</h4>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='text-align: center; color: #1E90FF; font-size: 3rem; margin-bottom: 30px;'>{meaning}</h1>", unsafe_allow_html=True)
            
            # 選擇測驗模式
            quiz_mode = st.radio("選擇測驗模式：", ["⌨️ 完整拼寫 (支援 Apple Pencil 隨手寫)", "🧩 字母填空"], horizontal=True)
            
            if quiz_mode == "🧩 字母填空":
                if 'masked_word' not in st.session_state or st.session_state.get('current_word_id') != word_id:
                    st.session_state.masked_word = generate_masked_word(word)
                    st.session_state.current_word_id = word_id
                st.markdown(f"<h2 style='text-align: center; letter-spacing: 5px; font-family: monospace;'>{st.session_state.masked_word}</h2>", unsafe_allow_html=True)
            
            user_input = st.text_input("在此輸入英文單字", key=f"input_{word_id}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 送出答案", use_container_width=True):
                    if user_input.strip().lower() == word.lower():
                        st.toast('答對了！進入下一個', icon='🎉')
                        update_word(conn, word_id, level, True, mistakes)
                        st.rerun()
                    else:
                        # 答錯了，進入看答案狀態
                        st.session_state.quiz_state = "show_wrong_answer"
                        update_word(conn, word_id, level, False, mistakes)
                        st.rerun()
            with col2:
                if st.button("❌ 不會拼 (看答案)", use_container_width=True):
                    st.session_state.quiz_state = "show_wrong_answer"
                    update_word(conn, word_id, level, False, mistakes)
                    st.rerun()

        # 狀態二：答錯或不會拼，顯示正確答案
        elif st.session_state.quiz_state == "show_wrong_answer":
            st.error("❌ 答錯了或忘記了！")
            st.markdown(f"<h4 style='text-align: center;'>「{meaning}」的正確答案是：</h4>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='text-align: center; color: #FF4B4B; font-size: 3.5rem;'>{word}</h1>", unsafe_allow_html=True)
            st.info("💡 沒關係！這個單字已經重新排入今日複習計畫，今天稍後會再次出現。")
            
            if st.button("👉 點我繼續測驗下一個單字", use_container_width=True):
                st.session_state.quiz_state = "question"
                st.rerun()

# --- 標籤頁 3: 弱點分析 ---
with tab3:
    st.header("你的單字庫與弱點追蹤")
    df = pd.read_sql_query('''
        SELECT 
            word AS 英文單字, 
            meaning AS 中文意思, 
            mistake_count AS 累積忘記次數,
            last_mistake_date AS 最近卡關日期,
            next_review_date AS 下次複習日
        FROM vocab 
        ORDER BY mistake_count DESC, last_mistake_date DESC
    ''', conn)
    
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.write("目前字庫還是空的。")
