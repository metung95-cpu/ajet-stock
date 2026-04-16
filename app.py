import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import re
import datetime

# ------------------------------------------------------------------
# 1. 기본 설정 및 보안 (로그인)
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 발주 관리 시스템", page_icon="🥩", layout="wide")

# 8시간 유지되는 서버 메모리
@st.cache_resource
def get_app_state():
    return {
        "logged_in": False,
        "login_expire_time": 0,
        "confirmed_indices": set() # 확정 내역(고유 ID) 보관
    }

app_state = get_app_state()

def check_login():
    current_time = time.time()
    
    if app_state["logged_in"] and current_time > app_state["login_expire_time"]:
        app_state["logged_in"] = False
        app_state["confirmed_indices"].clear()

    if not app_state["logged_in"]:
        st.title("🔒 에이젯 시스템 접속")
        with st.form("login_form"):
            user_id = st.text_input("아이디 (ID)")
            user_pw = st.text_input("비밀번호 (PW)", type="password")
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
            if submitted:
                if user_id == "AZ" and user_pw == "5835":
                    app_state["logged_in"] = True
                    app_state["login_expire_time"] = current_time + (8 * 3600)
                    st.success("인증되었습니다. 데이터를 불러옵니다...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("계정 정보가 일치하지 않습니다.")
        return False
    return True

if not check_login():
    st.stop()

# ------------------------------------------------------------------
# 2. 구글 시트 연결 및 데이터 로드
# ------------------------------------------------------------------
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def load_order_data():
    try:
        gc = get_gspread_client()
        sheet_key = '1bhfGQDzqA_W54CnWyVEXr07Ms74Yy3d1PctlVbZSVzk'
        doc = gc.open_by_key(sheet_key)
        all_sheets = doc.worksheets()
        target_worksheet = next((s for s in all_sheets if '4월' in s.title and '발주' in s.title), doc.get_worksheet(0))
        
        data = target_worksheet.get_all_values()
        if not data or len(data) < 1: return pd.DataFrame()
            
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip()
        df = df.loc[:, df.columns != '']
        
        item_col = "품명 브랜드 등급 EST"
        if item_col in df.columns:
            df[item_col] = df[item_col].astype(str).str.strip()
            df = df[~df[item_col].str.startswith(('냉', '.냉'))]
            df = df[df[item_col] != ""]
            
        qty_col = "수량(BOX)"
        if qty_col in df.columns:
            df[qty_col] = pd.to_numeric(df[qty_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).astype(int)
            df = df[df[qty_col] > 0]
            
        # 고유 식별자(UID) 생성 로직
        uid_cols = [c for c in df.columns if c in ['날짜', '시간', '거래처명', '담당자', '품명 브랜드 등급 EST', '수량(BOX)']]
        df['UID'] = df[uid_cols].astype(str).agg('_'.join, axis=1)
        df['UID'] = df['UID'] + "_" + df.groupby('UID').cumcount().astype(str)
        df.set_index('UID', inplace=True)
            
        return df
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 3. 메인 로직 및 탭 구성
# ------------------------------------------------------------------
st.title("🥩 AZ 발주확인(운영부)")

st.sidebar.success(f"현재 접속: AZ 관리자")
remaining_seconds = int(app_state["login_expire_time"] - time.time())
hours, remainder = divmod(remaining_seconds, 3600)
minutes, _ = divmod(remainder, 60)
st.sidebar.info(f"⏳ 자동 로그아웃까지:\n\n**{hours}시간 {minutes}분 남음**")

if st.sidebar.button("수동 로그아웃"):
    app_state["logged_in"] = False
    st.rerun()

raw_df = load_order_data()

if not raw_df.empty:
    date_col = next((c for c in raw_df.columns if '날짜' in c or '일자' in c or '일' in c), "날짜")
    item_col = "품명 브랜드 등급 EST"
    qty_col = "수량(BOX)"
    manager_col = "담당자"
    client_col = "거래처명"
    time_col = "시간"
    note_col = next((c for c in raw_df.columns if '비고' in c), "비고(이력,수기,취소)")
    add_col = next((c for c in raw_df.columns if '추가' in c), "추가")

    tab1, tab2, tab3 = st.tabs(["📦 출고 예정", "✅ 출고 확정", "📊 품목/담당자별 수량 현황"])

    # 💡 테블릿에서 짤리지 않게 최적화된 너비 설정
    base_col_config = {
        "👉 확정": st.column_config.CheckboxColumn("출고완료", width="small"),
        "👉 취소": st.column_config.CheckboxColumn("확정취소", width="small"),
        date_col: st.column_config.TextColumn("일자", width="small"),
        client_col: st.column_config.TextColumn("거래처명", width="medium"),
        manager_col: st.column_config.TextColumn("담당자", width="small"),
        item_col: st.column_config.TextColumn("품명", width="medium"),
        qty_col: st.column_config.NumberColumn("수량", width="small"),
        note_col: st.column_config.TextColumn("비고", width="medium"),
        add_col: st.column_config.TextColumn("추가", width="small"),
        time_col: st.column_config.TextColumn("시간", width="small")
    }

    def sort_dates(date_list):
        def parse_date(d):
            nums = re.findall(r'\d+', str(d))
            return tuple(map(int, nums)) if nums else (0, 0)
        return sorted(date_list, key=parse_date, reverse=True)

    today = datetime.datetime.now()
    today_m_d = f"{today.month}. {today.day}"
    today_d = str(today.day)

    # 탭 1: 출고 예정
    with tab1:
        if date_col in raw_df.columns:
            u_dates = [d for d in raw_df[date_col].unique() if str(d).strip() != '']
            sorted_dates = sort_dates(u_dates)
            
            default_index = 0
            for i, d in enumerate(sorted_dates):
                if today_m_d in str(d) or str(d).strip() == today_d:
                    default_index = i + 1
                    break
            
            selected_date_t1 = st.selectbox("📅 날짜 선택", ["전체 보기"] + sorted_dates, index=default_index, key="t1_date")
            pending_df = raw_df.copy()
            if selected_date_t1 != "전체 보기":
                pending_df = pending_df[pending_df[date_col] == selected_date_t1]
        else:
            pending_df = raw_df.copy()

        pending_df = pending_df[~pending_df.index.isin(app_state['confirmed_indices'])]
        
        if item_col in pending_df.columns:
            pending_df = pending_df.sort_values(by=[item_col])
        
        if not pending_df.empty:
            pending_df["👉 확정"] = False 
            
            # 💡 [핵심] 열 순서 변경: 출고완료가 날짜 바로 옆(왼쪽)으로 오도록 배치
            ordered_cols = ["👉 확정", date_col, client_col, manager_col, item_col, qty_col, note_col, add_col, time_col]
            display_pending = pending_df[[c for c in ordered_cols if c in pending_df.columns or c == "👉 확정"]]

            # 💡 use_container_width=True 로 테블릿 화면에 꽉 맞춤
            edited_df_t1 = st.data_editor(
                display_pending,
                column_config=base_col_config,
                disabled=[c for c in display_pending.columns if c != "👉 확정"],
                hide_index=True,
                use_container_width=True,
                height=int((len(display_pending) + 1) * 35) + 40,
                key="editor_pending"
            )

            confirmed_now = edited_df_t1[edited_df_t1["👉 확정"] == True].index
            if len(confirmed_now) > 0:
                app_state['confirmed_indices'].update(confirmed_now)
                st.toast(f"{len(confirmed_now)}건 확정 완료!")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("예정된 출고 건이 없습니다.")

    # 탭 2: 출고 확정
    with tab2:
        confirmed_df = raw_df[raw_df.index.isin(app_state['confirmed_indices'])].copy()
        if not confirmed_df.empty:
            confirmed_df["👉 취소"] = False
            
            # 💡 열 순서 변경 (출고완료 대신 확정취소 버튼 배치)
            ordered_cols_t2 = ["👉 취소", date_col, client_col, manager_col, item_col, qty_col, note_col, add_col, time_col]
            display_confirmed = confirmed_df[[c for c in ordered_cols_t2 if c in confirmed_df.columns or c == "👉 취소"]]

            edited_df_t2 = st.data_editor(
                display_confirmed,
                column_config=base_col_config,
                disabled=[c for c in display_confirmed.columns if c != "👉 취소"],
                hide_index=True,
                use_container_width=True,
                height=int((len(display_confirmed) + 1) * 35) + 40,
                key="editor_confirmed"
            )
            
            canceled_now = edited_df_t2[edited_df_t2["👉 취소"] == True].index
            if len(canceled_now) > 0:
                app_state['confirmed_indices'].difference_update(canceled_now)
                st.toast(f"{len(canceled_now)}건 확정 취소!")
                time.sleep(0.5)
                st.rerun()
        else:
            st.write("확정 내역이 없습니다.")

    # 탭 3: 집계 현황
    with tab3:
        all_pending = raw_df[~raw_df.index.isin(app_state['confirmed_indices'])]
        if not all_pending.empty:
            pivot_table = pd.pivot_table(
                all_pending, values=qty_col, index=item_col, columns=manager_col, aggfunc='sum', fill_value=0
            )
            pivot_table['총 합계'] = pivot_table.sum(axis=1)
            pivot_display = pivot_table.sort_values('총 합계', ascending=False).reset_index()
            
            st.dataframe(
                pivot_display, 
                use_container_width=True, 
                hide_index=True,
                height=int((len(pivot_display) + 1) * 35) + 40
            )
        else:
            st.write("집계할 데이터가 없습니다.")

else:
    st.info("발주 내역을 로딩 중입니다.")
