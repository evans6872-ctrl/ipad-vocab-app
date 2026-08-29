import streamlit as st
import psycopg2
from datetime import datetime, timedelta
import pandas as pd
import urllib.request

# 遺忘曲線間隔設定 (0代表今天重測，接著是1天、2天...)
INTERVALS = [0, 1, 2, 4, 7, 15, 30, 60]

# --- 1. 雲端資料庫連線與操作 ---
def get_db_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
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

def get_weak_words():
    conn = get_db_connection()
    c = conn.cursor()
    # 取出忘記次數大於0的單字，以次數最多者優先排列
    c.execute('SELECT id, word, meaning, level, mistake_count, image_data FROM vocab WHERE mistake_count > 0 ORDER BY mistake_count DESC')
    res = c.fetchall()
    conn.close()
    return res

def get_all_words_for_practice():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, word, meaning, level, mistake_count, image_data FROM vocab ORDER BY id DESC')
    res = c.fetchall()
    conn.close()
    return res

def update_word(word_id, level, remembered, mistake_count, clear_weakness=False):
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now().date()
    
    if remembered:
        new_level = min(level + 1, len(INTERVALS) - 1)
        next_review = today + timedelta(days=INTERVALS[new_level])
        if clear_weakness:
            # 弱點強化模式下答對，清空忘記次數，讓單字正式脫離弱點區！
            c.execute('UPDATE vocab SET level = %s, next_review_date = %s, mistake_count = 0 WHERE id = %s', 
                      (new_level, next_review, word_id))
        else:
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

def fetch_image_from_url(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read()
    except Exception:
        return None

# --- 2. Streamlit UI 介面 ---
st.set_page_config(page_title="遺忘曲線單字 App", page_icon="🧠", layout="centered")
init_db()

st.title("🧠 遺忘曲線單字記憶系統")

tab1, tab2, tab3, tab4 = st.tabs(["📝 新增單字", "🎯 測驗與練習", "📊 弱點分析", "🗂️ 總字庫管理"])

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

# --- 標籤頁 2: 測驗與練習 ---
with tab2:
    st.header("開始練習")
    practice_mode = st.radio("選擇練習模式：", ["📅 每日複習 (依計畫)", "🏋️ 強化弱點 (忘記次數>0)", "🔍 自訂單字練習"], horizontal=True)
    
    # 建立測驗狀態記憶區
    if 'quiz_state' not in st.session_state:
        st.session_state.quiz_state = 'question'
    if 'custom_index' not in st.session_state:
        st.session_state.custom_index = 0
    if 'queue_index' not in st.session_state:
        st.session_state.queue_index = 0
    if 'last_custom_selection' not in st.session_state:
        st.session_state.last_custom_selection = []
    if 'q_key' not in st.session_state:
        st.session_state.q_key = 0

    # 取得單字庫清單
    if practice_mode == "📅 每日複習 (依計畫)":
        words_list = get_due_words()
    elif practice_mode == "🏋️ 強化弱點 (忘記次數>0)":
        words_list = get_weak_words()
    else:
        all_words = get_all_words_for_practice()
        if all_words:
            word_options = {f"{w[1]} ({w[2]})": w for w in all_words}
            selected_keys = st.multiselect("請選擇要練習的單字（可多選）：", list(word_options.keys()))
            
            # 若選取的內容改變，重置自訂進度
            if selected_keys != st.session_state.last_custom_selection:
                st.session_state.custom_index = 0
                st.session_state.last_custom_selection = selected_keys
                st.session_state.quiz_state = 'question'
                
            words_list = [word_options[k] for k in selected_keys]
        else:
            words_list = []

    # 決定當前要測驗的單字
    current_word = None
    if practice_mode == "🔍 自訂單字練習":
        if st.session_state.custom_index < len(words_list):
            current_word = words_list[st.session_state.custom_index]
        elif len(words_list) > 0:
            st.success("🎉 您選取的自訂單字已全部練習完畢！您可以重新選擇單字繼續。")
    else:
        if words_list:
            # 確保 queue_index 不會超出當前單字清單的長度（讓錯誤單字可以循環重出）
            if st.session_state.queue_index >= len(words_list):
                st.session_state.queue_index = 0
            current_word = words_list[st.session_state.queue_index]
        else:
            st.success("🎉 太棒了！目前這個模式下沒有待測驗的單字。")
            st.session_state.quiz_state = 'question'

    # 開始測驗介面
    if current_word:
        word_id, word, meaning, level, mistakes, image_data = current_word
        
        if st.session_state.quiz_state == 'question':
            if practice_mode != "🔍 自訂單字練習":
                st.write(f"待測驗數量：**{len(words_list)}**")
                
            st.markdown(f"<h4 style='text-align: center; color: #666;'>請輸入以下中文對應的英文：</h4>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='text-align: center; color: #1E90FF; font-size: 3rem;'>{meaning}</h1>", unsafe_allow_html=True)
            
            if image_data:
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.image(bytes(image_data), use_container_width=True)
            
            # 使用表單包裝，在電腦或 iPad 鍵盤上按下 Enter 就能直接送出答案
            with st.form(key=f"quiz_form_{st.session_state.q_key}"):
                user_ans = st.text_input("📝 請在此輸入英文拼寫：")
                
                col1, col2 = st.columns(2)
                with col1:
                    submit_btn = st.form_submit_button("✅ 送出答案", use_container_width=True)
                with col2:
                    give_up_btn = st.form_submit_button("❌ 不會拼 (看答案)", use_container_width=True)
                    
                if submit_btn:
                    if user_ans.strip().lower() == word.lower():
                        st.toast("答對了！", icon="🎉")
                        # 答對時的處理
                        is_weakness = (practice_mode == "🏋️ 強化弱點 (忘記次數>0)")
                        update_word(word_id, level, True, mistakes, clear_weakness=is_weakness)
                        
                        if practice_mode == "🔍 自訂單字練習":
                            st.session_state.custom_index += 1
                        # 注意：每日或弱點模式下，答對的單字會直接從 words_list 消失，所以 queue_index 不用加 1，下一個單字會自動遞補上來
                        
                        st.session_state.q_key += 1
                        st.session_state.quiz_state = 'question'
                        st.rerun()
                    else:
                        st.session_state.quiz_state = 'wrong_feedback'
                        update_word(word_id, level, False, mistakes)
                        st.rerun()
                        
                if give_up_btn:
                    st.session_state.quiz_state = 'wrong_feedback'
                    update_word(word_id, level, False, mistakes)
                    st.rerun()
                    
        elif st.session_state.quiz_state == 'wrong_feedback':
            st.error("❌ 拼錯了或是忘記囉！請看正確答案並加深記憶：")
            st.markdown(f"<h4 style='text-align: center;'>「{meaning}」的正確英文是：</h4>", unsafe_allow_html=True)
            st.markdown(f"<h1 style='text-align: center; color: #FF4B4B; font-size: 3.5rem; letter-spacing: 2px;'>{word}</h1>", unsafe_allow_html=True)
            
            if image_data:
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.image(bytes(image_data), use_container_width=True)
            
            if st.button("👉 我記住了，前往下一題", use_container_width=True):
                if practice_mode == "🔍 自訂單字練習":
                    st.session_state.custom_index += 1
                else:
                    # 答錯時 queue_index 往後加 1，把剛剛答錯的字排到後面去，稍後會循環重出
                    st.session_state.queue_index += 1
                    
                st.session_state.q_key += 1
                st.session_state.quiz_state = 'question'
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
