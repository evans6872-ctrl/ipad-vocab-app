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
    
    # --- 初始化核心狀態 ---
    if 'quiz_state' not in st.session_state:
        st.session_state.quiz_state = 'question'
    if 'current_test_word' not in st.session_state:
        st.session_state.current_test_word = None # 用來「鎖定」當前題目的字典
    if 'last_practice_mode' not in st.session_state:
        st.session_state.last_practice_mode = practice_mode

    # 如果切換了模式，重置狀態以避免卡題
    if st.session_state.last_practice_mode != practice_mode:
        st.session_state.quiz_state = 'question'
        st.session_state.current_test_word = None
        st.session_state.last_practice_mode = practice_mode

    # 根據選擇的模式抓取單字清單
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

    # --- 核心邏輯：判斷是否需要載入新題目 ---
    needs_new_word = False
    
    # 只有在正常的「問答狀態」下，我們才允許更換題目
    if st.session_state.quiz_state == 'question':
        if st.session_state.current_test_word is None:
            needs_new_word = True
        else:
            # 檢查目前鎖定的單字是否還在待測清單中
            # 如果不在了(例如在自訂模式中切換了下拉選單)，就強制更新題目
            current_id = st.session_state.current_test_word['id']
            if not any(w[0] == current_id for w in words_list):
                needs_new_word = True
    
    # 將新題目「鎖定」到 session_state 中
    if needs_new_word:
        if words_list:
            w = words_list[0]
            st.session_state.current_test_word = {
                "id": w[0], "word": w[1], "meaning": w[2], 
                "level": w[3], "mistakes": w[4]
            }
        else:
            st.session_state.current_test_word = None

    # --- 畫面渲染與作答邏輯 ---
    if st.session_state.current_test_word is None:
        if st.session_state.quiz_state != 'wrong_feedback':
            st.info("太棒了！目前這個模式下沒有待測驗的單字。🎉")
    else:
        # 從鎖定的狀態中讀取單字資訊（這保證了即使資料庫更新，這裡的值也不會變）
        word_info = st.session_state.current_test_word
        word_id = word_info['id']
        word = word_info['word']
        meaning = word_info['meaning']
        level = word_info['level']
        mistakes = word_info['mistakes']

        # 狀態一：顯示題目
        if st.session_state.quiz_state == 'question':
            if practice_mode != "🔍 自訂單字練習":
                st.write(f"待複習數量：**{len(words_list)}**")
            
            st.markdown(f"<h3 style='text-align: center; color: #555;'>「{meaning}」的正確英文是：</h3>", unsafe_allow_html=True)
            
            user_answer = st.text_input("請輸入英文單字：", key=f"input_{word_id}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("送出答案", use_container_width=True):
                    if user_answer.strip().lower() == word.lower():
                        # 答對了
                        update_word(conn, word_id, level, True, mistakes)
                        st.session_state.current_test_word = None # 清空鎖定，讓系統抓下一題
                        st.rerun()
                    else:
                        # 答錯了：更新資料庫，但**不**清空 current_test_word，強制進入檢討模式
                        update_word(conn, word_id, level, False, mistakes)
                        st.session_state.quiz_state = 'wrong_feedback'
                        st.rerun()
            with col2:
                if st.button("不會，直接看答案", use_container_width=True):
                    # 放棄作答：更新資料庫，保留 current_test_word 進入檢討模式
                    update_word(conn, word_id, level, False, mistakes)
                    st.session_state.quiz_state = 'wrong_feedback'
                    st.rerun()

        # 狀態二：檢討畫面
        elif st.session_state.quiz_state == 'wrong_feedback':
            st.error("❌ 拼錯了或是忘記囉！請看正確答案並加深記憶：")
            
            # 這裡的 meaning 和 word 都是從被鎖定的 current_test_word 拿出來的，絕對不會變成下一題
            st.markdown(f"<h3 style='text-align: center; color: #555;'>「{meaning}」的正確英文是：</h3>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='text-align: center; color: #FF4B4B; font-size: 4rem; font-weight: bold;'>{word}</h2>", unsafe_allow_html=True)
            
            if st.button("👉 我記住了，前往下一題", use_container_width=True):
                st.session_state.quiz_state = 'question'
                st.session_state.current_test_word = None # 這時才清空鎖定，正式放行下一題
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
