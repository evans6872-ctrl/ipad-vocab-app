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
            mistake_count INTEGER,
            group_name TEXT
        )
    ''')
    # 相容舊資料庫，若無 group_name 欄位則自動補上
    try:
        c.execute('ALTER TABLE vocab ADD COLUMN group_name TEXT')
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn

def add_single_word(conn, word, meaning, group_name):
    c = conn.cursor()
    today = datetime.now().date()
    try:
        c.execute('''
            INSERT INTO vocab (word, meaning, level, next_review_date, mistake_count, group_name)
            VALUES (?, ?, 0, ?, 0, ?)
        ''', (word, meaning, today, group_name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def add_batch_words(conn, raw_text, group_name):
    c = conn.cursor()
    today = datetime.now().date()
    lines = raw_text.strip().split('\n')
    success_count = 0
    duplicate_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 支援逗號或空格分隔 (例如: apple,蘋果 或 apple 蘋果)
        if ',' in line:
            parts = line.split(',', 1)
        else:
            parts = line.split(None, 1)
            
        if len(parts) == 2:
            word = parts[0].strip().lower()
            meaning = parts[1].strip()
            try:
                c.execute('''
                    INSERT INTO vocab (word, meaning, level, next_review_date, mistake_count, group_name)
                    VALUES (?, ?, 0, ?, 0, ?)
                ''', (word, meaning, today, group_name))
                success_count += 1
            except sqlite3.IntegrityError:
                duplicate_count += 1
    conn.commit()
    return success_count, duplicate_count

def get_due_words(conn):
    c = conn.cursor()
    today = datetime.now().date()
    c.execute('SELECT id, word, meaning, level, mistake_count, group_name FROM vocab WHERE next_review_date <= ?', (today,))
    return c.fetchall()

def get_weak_words(conn):
    c = conn.cursor()
    c.execute('SELECT id, word, meaning, level, mistake_count, group_name FROM vocab WHERE mistake_count > 0 ORDER BY mistake_count DESC')
    return c.fetchall()

def get_all_words(conn):
    c = conn.cursor()
    try:
        c.execute('SELECT id, word, meaning, level, next_review_date, mistake_count, group_name FROM vocab ORDER BY id DESC')
        rows = c.fetchall()
        return [r if len(r) == 7 else r + ('預設群組',) for r in rows]
    except sqlite3.OperationalError:
        c.execute('SELECT id, word, meaning, level, next_review_date, mistake_count FROM vocab ORDER BY id DESC')
        rows = c.fetchall()
        return [r + ('預設群組',) for r in rows]

def get_all_groups(conn):
    c = conn.cursor()
    c.execute('SELECT DISTINCT group_name FROM vocab WHERE group_name IS NOT NULL AND group_name != ""')
    rows = c.fetchall()
    return [r[0] for r in rows]

def get_words_by_group(conn, group_name):
    c = conn.cursor()
    c.execute('SELECT id, word, meaning, level, mistake_count, group_name FROM vocab WHERE group_name = ?', (group_name,))
    return c.fetchall()

def delete_word_by_id(conn, word_id):
    c = conn.cursor()
    c.execute('DELETE FROM vocab WHERE id = ?', (word_id,))
    conn.commit()

def update_word(conn, word_id, level, remembered, mistake_count):
    c = conn.cursor()
    if remembered:
        new_level = min(level + 1, len(INTERVALS) - 1)
    else:
        new_level = 0 
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

tab1, tab2, tab3 = st.tabs(["📝 新增單字", "🎯 測驗與練習", "📊 單字庫與弱點管理"])

# --- 標籤頁 1: 新增單字 (支援單字/批次與群組) ---
with tab1:
    st.header("輸入新單字")
    
    add_type = st.radio("新增模式", ["單筆新增", "批次新增 (多行)"], horizontal=True)
    group_input = st.text_input("群組名稱 (例如: 英文第一課)", value="預設群組")
    
    if add_type == "單筆新增":
        with st.form("single_add_form"):
            new_word = st.text_input("英文單字")
            new_meaning = st.text_input("中文意思")
            submitted = st.form_submit_button("加入計畫")
            
            if submitted:
                if new_word and new_meaning:
                    success = add_single_word(conn, new_word.strip().lower(), new_meaning.strip(), group_input.strip())
                    if success:
                        st.success(f"已成功加入單字：{new_word} (群組: {group_input})")
                    else:
                        st.error("這個單字已經在字庫中囉！")
                else:
                    st.warning("請填寫單字與意思。")
    else:
        with st.form("batch_add_form"):
            st.caption("格式範例：每行一組，可用逗號或空格分隔。\napple,蘋果\nbanana 香蕉")
            batch_text = st.text_area("批次單字清單")
            batch_submitted = st.form_submit_button("批次加入計畫")
            
            if batch_submitted:
                if batch_text.strip():
                    succ, dup = add_batch_words(conn, batch_text, group_input.strip())
                    st.success(f"批次加入完成！成功新增 {succ} 個單字，重複略過 {dup} 個。")
                else:
                    st.warning("請輸入要新增的單字清單。")

# --- 標籤頁 2: 測驗與練習 ---
with tab2:
    st.header("開始練習")
    
    practice_mode = st.radio("選擇練習模式：", 
                               ["📅 每日複習 (依計畫)", "🏋️ 強化弱點 (忘記次數>0)", "🔍 自訂單字練習"], 
                               horizontal=True)
    
    words_list = []
    
    if practice_mode == "📅 每日複習 (依計畫)":
        words_list = get_due_words(conn)
    elif practice_mode == "🏋️ 強化弱點 (忘記次數>0)":
        words_list = get_weak_words(conn)
    else:
        st.subheader("自訂單字練習選項")
        custom_sub_mode = st.radio("自訂選取方式：", ["依群組選擇", "自由勾選多個單字"], horizontal=True)
        
        all_words = get_all_words(conn)
        if all_words:
            if custom_sub_mode == "依群組選擇":
                groups = get_all_groups(conn)
                if groups:
                    selected_group = st.selectbox("選擇群組：", groups)
                    words_list = get_words_by_group(conn, selected_group)
                else:
                    st.info("目前沒有任何群組分類。")
            else:
                # 多選單字
                word_options = {f"{w[1]} ({w[2]}) [群組: {w[5] or '無'}]": w for w in all_words}
                selected_keys = st.multiselect("請選擇要練習的單字（可複選）：", list(word_options.keys()))
                words_list = [word_options[k] for k in selected_keys]
        else:
            words_list = []

    # 初始化核心狀態
    if 'quiz_state' not in st.session_state:
        st.session_state.quiz_state = 'question'
    if 'current_test_word' not in st.session_state:
        st.session_state.current_test_word = None 
    if 'last_practice_mode' not in st.session_state:
        st.session_state.last_practice_mode = practice_mode

    if st.session_state.last_practice_mode != practice_mode:
        st.session_state.quiz_state = 'question'
        st.session_state.current_test_word = None
        st.session_state.last_practice_mode = practice_mode

    needs_new_word = False
    if st.session_state.quiz_state == 'question':
        if st.session_state.current_test_word is None:
            needs_new_word = True
        else:
            current_id = st.session_state.current_test_word['id']
            if not any(w[0] == current_id for w in words_list):
                needs_new_word = True
    
    if needs_new_word:
        if words_list:
            w = words_list[0]
            st.session_state.current_test_word = {
                "id": w[0], "word": w[1], "meaning": w[2], 
                "level": w[3], "mistakes": w[4], "group": w[5]
            }
        else:
            st.session_state.current_test_word = None

    if st.session_state.current_test_word is None:
        if st.session_state.quiz_state != 'wrong_feedback':
            st.info("太棒了！目前這個模式下沒有待測驗的單字。🎉")
    else:
        word_info = st.session_state.current_test_word
        word_id = word_info['id']
        word = word_info['word']
        meaning = word_info['meaning']
        level = word_info['level']
        mistakes = word_info['mistakes']
        group = word_info['group']

        if st.session_state.quiz_state == 'question':
            if practice_mode != "🔍 自訂單字練習":
                st.write(f"待複習數量：**{len(words_list)}**")
            elif group:
                st.caption(f"目前群組：{group}")
            
            st.markdown(f"<h3 style='text-align: center; color: #555;'>「{meaning}」的正確英文是：</h3>", unsafe_allow_html=True)
            
            user_answer = st.text_input("請輸入英文單字：", key=f"input_{word_id}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("送出答案", use_container_width=True):
                    if user_answer.strip().lower() == word.lower():
                        update_word(conn, word_id, level, True, mistakes)
                        st.session_state.current_test_word = None 
                        st.rerun()
                    else:
                        update_word(conn, word_id, level, False, mistakes)
                        st.session_state.quiz_state = 'wrong_feedback'
                        st.rerun()
            with col2:
                if st.button("不會，直接看答案", use_container_width=True):
                    update_word(conn, word_id, level, False, mistakes)
                    st.session_state.quiz_state = 'wrong_feedback'
                    st.rerun()

        elif st.session_state.quiz_state == 'wrong_feedback':
            st.error("❌ 拼錯了或是忘記囉！請看正確答案並加深記憶：")
            
            st.markdown(f"<h3 style='text-align: center; color: #555;'>「{meaning}」的正確英文是：</h3>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='text-align: center; color: #FF4B4B; font-size: 4rem; font-weight: bold;'>{word}</h2>", unsafe_allow_html=True)
            
            if st.button("👉 我記住了，前往下一題", use_container_width=True):
                st.session_state.quiz_state = 'question'
                st.session_state.current_test_word = None 
                st.rerun()

# --- 標籤頁 3: 單字庫與弱點管理 (含查詢與刪除) ---
with tab3:
    st.header("📚 單字庫管理與弱點分析")
    
    all_data = get_all_words(conn)
    if all_data:
        df = pd.DataFrame(all_data, columns=["ID", "英文單字", "中文意思", "記憶級別", "下次複習日", "忘記次數", "群組名稱"])
        
        # 搜尋與篩選工具
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            search_query = st.text_input("🔍 搜尋單字或意思：", "").strip().lower()
        with col_s2:
            groups_filter = ["全部"] + get_all_groups(conn)
            selected_group_filter = st.selectbox("📂 依群組篩選：", groups_filter)
            
        filtered_df = df.copy()
        if search_query:
            filtered_df = filtered_df[
                filtered_df["英文單字"].str.lower().str.contains(search_query) | 
                filtered_df["中文意思"].str.lower().str.contains(search_query)
            ]
        if selected_group_filter != "全部":
            filtered_df = filtered_df[filtered_df["群組名稱"] == selected_group_filter]
            
        st.dataframe(filtered_df[["英文單字", "中文意思", "群組名稱", "記憶級別", "下次複習日", "忘記次數"]], use_container_width=True)
        st.caption("「忘記次數」越高的單字，代表是你最常忘記的弱點喔！")
        
        st.markdown("---")
        st.subheader("🗑️ 刪除單字管理")
        delete_options = {f"{row[1]} ({row[2]}) [群組: {row[6] or '無'}] (ID: {row[0]})": row[0] for row in filtered_df.itertuples(index=False)}
        
        if delete_options:
            selected_to_delete = st.selectbox("選擇要刪除的單字：", list(delete_options.keys()))
            if st.button("確定刪除此單字", type="primary"):
                target_id = delete_options[selected_to_delete]
                delete_word_by_id(conn, target_id)
                st.success(f"已成功刪除單字！")
                st.rerun()
        else:
            st.info("目前沒有符合條件的單字可供刪除。")
    else:
        st.write("目前字庫還是空的。")
