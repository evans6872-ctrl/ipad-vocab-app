import streamlit as st
import psycopg2
from datetime import datetime, timedelta
import pandas as pd
import random
import urllib.request

# 遺忘曲線間隔設定 (0代表今天重測，接著是1天、2天...)
INTERVALS = [0, 1, 2, 4, 7, 15, 30, 60]

# --- 1. 雲端資料庫連線與操作 ---
def get_db_connection():
    # 透過 Streamlit Secrets 讀取您剛剛設定的資料庫網址
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # PostgreSQL 語法：AUTOINCREMENT 改為 SERIAL，BLOB 改為 BYTEA
    c.execute('''
        CREATE TABLE IF NOT EXISTS vocab (
            id SERIAL PRIMARY KEY,
            word TEXT UNIQUE,
            meaning TEXT,
            level INTEGER,
            next_review_date DATE,
            mistake_count INTEGER,
            last_mistake_date DATE,
            image_data BYTEA
        )
    ''')
    conn.commit()
    conn.close()

def add_word(word, meaning, image_data=None):
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now().date()
    try:
        img_val = psycopg2.Binary(image_data) if image_data else None
        # PostgreSQL 使用 %s 作為變數佔位符
        c.execute('''
            INSERT INTO vocab (word, meaning, level, next_review_date, mistake_count, image_data)
            VALUES (%s, %s, 0, %s, 0, %s)
        ''', (word, meaning, today, img_val))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()

def get_due_words():
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now().date()
    c.execute('SELECT id, word, meaning, level, mistake_count, image_data FROM vocab WHERE next_review_date <= %s ORDER BY next_review_date ASC', (today,))
    res = c.fetchall()
    conn.close()
    return res

def update_word(word_id, level, remembered, mistake_count):
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now().date()
    
    if remembered:
        new_level = min(level + 1, len(INTERVALS) - 1)
        next_review = today + timedelta(days=INTERVALS[new_level])
        c.execute('UPDATE vocab SET level = %s, next_review_date = %s WHERE id = %s', 
                  (new_level, next_review, word_id))
    else:
        new_level = 0
        mistake_count += 1
        next_review = today + timedelta(days=INTERVALS[new_level])
        c.execute('UPDATE vocab SET level = %s, next_review_date = %s, mistake_count = %s, last_mistake_date = %s WHERE id = %s', 
                  (new_level, next_review, mistake_count, today, word_id))
    conn.commit()
    conn.close()

def get_total_count():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM vocab")
    res = c.fetchone()[0]
    conn.close()
    return res

def get_all_words():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, word, meaning FROM vocab ORDER BY id DESC")
    res = c.fetchall()
    conn.close()
    return res

def update_word_info(word_id, new_word, new_meaning, new_image_data=None, clear_image=False):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if clear_image:
            c.execute("UPDATE vocab SET word = %s, meaning = %s, image_data = NULL WHERE id = %s", (new_word, new_meaning, word_id))
        elif new_image_data:
            img_val = psycopg2.Binary(new_image_data)
            c.execute("UPDATE vocab SET word = %s, meaning = %s, image_data = %s WHERE id = %s", (new_word, new_meaning, img_val, word_id))
        else:
            c.execute("UPDATE vocab SET word = %s, meaning = %s WHERE id = %s", (new_word, new_meaning, word_id))
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_word(word_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM vocab WHERE id = %s", (word_id,))
    conn.commit()
    conn.close()
    
def get_weakness_df():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        SELECT 
            word AS 英文單字, 
            meaning AS 中文意思, 
            mistake_count AS 累積忘記次數,
            last_mistake_date AS 最近卡關日期
        FROM vocab 
        ORDER BY mistake_count DESC, last_mistake_date DESC
    ''')
    rows = c.fetchall()
    cols = [desc[0] for desc in c.description]
    conn.close()
    return pd.DataFrame(rows, columns=cols)
    
def get_all_df():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id AS 編號, word AS 英文, meaning AS 中文, level AS 記憶階段 FROM vocab ORDER BY id DESC')
    rows = c.fetchall()
    cols = [desc[0] for desc in c.description]
    conn.close()
    return pd.DataFrame(rows, columns=cols)

def generate_masked_word(word):
    if len(word) <= 2:
        return " _ " * len(word)
    word_list = list(word)
    hide_count = max(1, len(word) // 2)
    available_indices = list(range(1, len(word)))
    if not available_indices:
        available_indices = [0]
    hide_indices = random.sample(available_indices, min(hide_count, len(available_indices)))
    for i in hide_indices:
        if word_list[i].isalpha():
            word_list[i] = "_"
    return " ".join(word_list)

def fetch_image_from_url(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read()
    except Exception:
        return None

# --- 2. Streamlit UI 介面 ---
st.set_page_config(page_title="遺忘曲線單字 App", page_icon="🧠", layout="centered")

# 啟動時自動建立雲端資料表
init_db()

st.title("🧠 遺忘曲線單字記憶系統")

tab1, tab2, tab3, tab4 = st.tabs(["📝 新增單字", "🎯 今日測驗", "📊 弱點分析", "🗂️ 總字庫管理"])

# --- 標籤頁 1: 新增單字 ---
with tab1:
    st.header("新增單字庫")
    st.subheader("🔹 單筆輸入 (支援電腦複製貼上)")
    with st.form("add_word_form"):
        new_word = st.text_input("英文單字")
        new_meaning = st.text_input("中文意思")
        
        st.write("🖼️ **加入圖片方式 (電腦用戶可直接 Ctrl+V)：**")
        image_url = st.text_input("🔗 方式一：貼上網路圖片網址")
        uploaded_image = st.file_uploader("📂 方式二：點擊此處並按 Ctrl+V 貼上截圖，或選擇檔案", type=['png', 'jpg', 'jpeg'])
        
        if st.form_submit_button("單筆加入"):
            if new_word and new_meaning:
                img_bytes = None
                
                if uploaded_image:
                    img_bytes = uploaded_image.getvalue()
                elif image_url.strip():
                    img_bytes = fetch_image_from_url(image_url.strip())
                    if not img_bytes:
                        st.warning("⚠️ 無法讀取該網址的圖片，已為您加入單字，但未包含圖片。")

                if add_word(new_word.strip().lower(), new_meaning.strip(), img_bytes):
                    st.success(f"已加入：{new_word}")
                else:
                    st.error("單字已在字庫中！")

    st.divider()
    st.subheader("🔹 批量加入 (僅限文字)")
    bulk_input = st.text_area("格式：英文,中文 (每行一個)", placeholder="apple,蘋果\nbanana,香蕉", height=120)
    if st.button("🚀 批量加入計畫"):
        if bulk_input.strip():
            success_count, fail_count = 0, 0
            for line in bulk_input.strip().split('\n'):
                delimiter = ',' if ',' in line else '，'
                parts = line.split(delimiter)
                if len(parts) >= 2:
                    if add_word(parts[0].strip().lower(), parts[1].strip()):
                        success_count += 1
                    else:
                        fail_count += 1
            st.success(f"成功加入 {success_count} 個單字，{fail_count} 個單字已存在。")

# --- 標籤頁 2: 今日測驗 ---
with tab2:
    st.header("今日需複習單字")
    due_words = get_due_words()
    
    if 'quiz_state' not in st.session_state:
        st.session_state.quiz_state = "question"
    
    if not due_words:
        st.info("太棒了！今天的任務全數完成囉！🎉")
        st.session_state.quiz_state = "question"
    else:
        st.write(f"還有 **{len(due_words)}** 個單字待測驗")
        current_word = due_words[0]
        word_id, word, meaning, level, mistakes, image_data = current_word
        
        if st.session_state.quiz_state == "question":
            st.markdown(f"<h4 style='text-align: center; color: #666;'>請問這個中文的英文是什麼？</h4>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='text-align: center; color: #1E90FF; font-size: 3rem; margin-bottom: 10px;'>{meaning}</h1>", unsafe_allow_html=True)
            
            if image_data:
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    # 轉換資料庫儲存的二進制格式讓 Streamlit 正確顯示圖片
                    st.image(bytes(image_data), use_container_width=True)
            
            quiz_mode = st.radio("選擇測驗模式：", ["⌨️ 完整拼寫 (支援 Apple Pencil)", "🧩 字母填空"], horizontal=True)
            
            if quiz_mode == "🧩 字母填空":
                if 'masked_word' not in st.session_state or st.session_state.get('current_word_id') != word_id:
                    st.session_state.masked_word = generate_masked_word(word)
                    st.session_state.current_word_id = word_id
                st.markdown(f"<h2 style='text-align: center; letter-spacing: 5px; font-family: monospace;'>{st.session_state.masked_word}</h2>", unsafe_allow_html=True)
            
            user_input = st.text_input("在此輸入英文單字", key=f"input_{word_id}")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ 送出答案", use_container_width=True):
                    if user_input.strip().lower() == word.lower():
                        st.toast('答對了！進入下一個', icon='🎉')
                        update_word(word_id, level, True, mistakes)
                        st.rerun()
                    else:
                        st.session_state.quiz_state = "show_wrong_answer"
                        update_word(word_id, level, False, mistakes)
                        st.rerun()
            with col_b:
                if st.button("❌ 不會拼 (看答案)", use_container_width=True):
                    st.session_state.quiz_state = "show_wrong_answer"
                    update_word(word_id, level, False, mistakes)
                    st.rerun()

        elif st.session_state.quiz_state == "show_wrong_answer":
            st.error("❌ 答錯了或忘記了！")
            st.markdown(f"<h4 style='text-align: center;'>「{meaning}」的正確答案是：</h4>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='text-align: center; color: #FF4B4B; font-size: 3.5rem;'>{word}</h1>", unsafe_allow_html=True)
            
            if image_data:
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.image(bytes(image_data), use_container_width=True)
                    
            st.info("💡 這個單字已經重新排入今日複習計畫，今天稍後會再次出現。")
            if st.button("👉 點我繼續測驗下一個單字", use_container_width=True):
                st.session_state.quiz_state = "question"
                st.rerun()

# --- 標籤頁 3: 弱點分析 ---
with tab3:
    st.header("弱點追蹤")
    df = get_weakness_df()
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.write("目前字庫還是空的。")

# --- 標籤頁 4: 總字庫管理 ---
with tab4:
    st.header("🗂️ 總字庫與管理")
    
    total_words = get_total_count()
    st.info(f"📚 目前資料庫中共有 **{total_words}** 個單字")
    
    st.subheader("✏️ 編輯或刪除單字")
    all_words_list = get_all_words()
    
    if all_words_list:
        word_options = {f"{w[1]} ({w[2]})": w for w in all_words_list}
        selected_option = st.selectbox("請尋找並選擇要處理的單字：", options=list(word_options.keys()))
        selected_id, selected_word, selected_meaning = word_options[selected_option]
        
        col1, col2 = st.columns(2)
        with col1:
            with st.form("edit_form"):
                st.write("📝 修改單字內容")
                edit_word = st.text_input("英文", value=selected_word)
                edit_meaning = st.text_input("中文", value=selected_meaning)
                
                st.write("🖼️ **更換圖片 (擇一，若不換請留空)：**")
                edit_image_url = st.text_input("🔗 貼上新圖片網址")
                edit_image_file = st.file_uploader("📂 點擊此處按 Ctrl+V 貼上新圖片", type=['png', 'jpg', 'jpeg'])
                clear_img_checkbox = st.checkbox("🗑️ 清除此單字原本的圖片")
                
                if st.form_submit_button("💾 儲存修改", use_container_width=True):
                    img_bytes_to_update = None
                    if edit_image_file:
                        img_bytes_to_update = edit_image_file.getvalue()
                    elif edit_image_url.strip():
                        img_bytes_to_update = fetch_image_from_url(edit_image_url.strip())
                    
                    if update_word_info(selected_id, edit_word.strip().lower(), edit_meaning.strip(), img_bytes_to_update, clear_img_checkbox):
                        st.success("修改成功！")
                        st.rerun()
                    else:
                        st.error("修改失敗（可能是修改後的英文已存在於字庫中）")
        with col2:
            with st.form("delete_form"):
                st.write("🗑️ 刪除此單字")
                st.warning("⚠️ 刪除後無法復原。")
                st.text_input("確認", value="勾選下方按鈕刪除", disabled=True, label_visibility="hidden")
                if st.form_submit_button("🚨 確認永久刪除", use_container_width=True):
                    delete_word(selected_id)
                    st.success("刪除成功！")
                    st.rerun()
                    
    st.divider()
    st.write("📋 **所有單字預覽**")
    df_all = get_all_df()
    if not df_all.empty:
        st.dataframe(df_all, use_container_width=True, hide_index=True)
