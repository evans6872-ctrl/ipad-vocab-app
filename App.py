import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd

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
    
    # 自動升級資料庫：加入「最後忘記日期」欄位 (如果已存在則略過)
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

# --- 2. Streamlit UI 介面 ---
st.set_page_config(page_title="遺忘曲線單字 App", page_icon="🧠", layout="centered")

conn = init_db()
st.title("🧠 遺忘曲線單字記憶系統")

tab1, tab2, tab3 = st.tabs(["📝 新增單字", "🎯 今日測驗", "📊 弱點分析"])

# --- 標籤頁 1: 新增單字 ---
with tab1:
    st.header("新增單字庫")
    
    st.subheader("🔹 方式一：大量匯入")
    bulk_input = st.text_area("格式：英文,中文 (每行一個)", placeholder="apple,蘋果\nbanana,香蕉\ncat,貓咪", height=150)
    if st.button("🚀 批量加入計畫"):
        if bulk_input.strip():
            success_count, fail_count = 0, 0
            for line in bulk_input.strip().split('\n'):
                if ',' in line or '，' in line:
                    # 支援半形與全形逗號
                    delimiter = ',' if ',' in line else '，'
                    parts = line.split(delimiter)
                    if len(parts) >= 2:
                        w = parts[0].strip().lower()
                        m = parts[1].strip()
                        if add_word(conn, w, m):
                            success_count += 1
                        else:
                            fail_count += 1
            st.success(f"匯入完成！成功加入 {success_count} 個單字，{fail_count} 個單字已存在。")
        else:
            st.warning("請先輸入內容喔！")

    st.divider()
    
    st.subheader("🔹 方式二：單筆輸入")
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
    
    if not due_words:
        st.info("太棒了！今天的任務全數完成囉！🎉")
    else:
        st.write(f"還有 **{len(due_words)}** 個單字待複習（包含今天答錯的單字）")
        
        current_word = due_words[0]
        word_id, word, meaning, level, mistakes = current_word
        
        st.markdown(f"<h2 style='text-align: center; color: #1E90FF; font-size: 3rem;'>{word}</h2>", unsafe_allow_html=True)
        
        if st.checkbox("顯示答案"):
            st.success(f"**中文意思:** {meaning}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("❌ 忘記了 (今天稍後重測)", use_container_width=True):
                    update_word(conn, word_id, level, False, mistakes)
                    st.rerun()
            with col2:
                if st.button("✅ 記得了 (進入下一階段)", use_container_width=True):
                    update_word(conn, word_id, level, True, mistakes)
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
        st.caption("💡 提示：你可以點擊欄位標題來進行排序。只要「最近卡關日期」集中在某幾天，就代表那天的學習狀況可能比較疲勞喔！")
    else:
        st.write("目前字庫還是空的。")
