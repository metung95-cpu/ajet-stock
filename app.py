import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

st.set_page_config(page_title="에이젯 재고관리", layout="wide")

# --- 구글 인증 ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
    return gspread.authorize(credentials)

# --- 데이터 로딩 (이미 있는 재고 불러오기) ---
@st.cache_data(ttl=600)
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = df.columns.str.strip() # 공백 제거
    # 유통기한 기준 정렬용 임시 컬럼 생성
    df['유통기한_dt'] = pd.to_datetime(df['유통기한'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
    return df

# --- 출고 저장 함수 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 로그인 (생략 가능, 기존 코드 유지) ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.title("🔐 에이젯 재고관리 로그인")
    u_id = st.text_input("아이디")
    u_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        if (u_id == "AZ" and u_pw == "5835") or (u_id == "AZS" and u_pw == "0983"):
            st.session_state.logged_in = True
            st.session_state.user_role = u_id
            st.rerun()
    st.stop()

# --- 1. 재고 데이터 확보 ---
df = load_inventory()

st.title("📦 에이젯 실시간 재고 현황")
# (상단 재고 조회 화면은 기존과 동일하게 유지...)
st.dataframe(df.drop(columns=['유통기한_dt']), use_container_width=True, hide_index=True)

# --- 2. 출고 등록 (AZS 전용) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    # 🔍 품목 검색 (재고 데이터에서 필터링)
    item_search = st.text_input("출고할 품목 검색 (예: 삼겹양지)", key="outbound_search")
    
    selected_row = None
    if item_search:
        # [핵심] 불러온 df에서 검색어가 포함된 재고만 골라 유통기한순 정렬
        selection_df = df[df['품명'].str.contains(item_search, na=False)].sort_values(by='유통기한_dt')
        
        if not selection_df.empty:
            # 드롭다운에 보여줄 정보 정리
            selection_df['label'] = selection_df.apply(
                lambda x: f"[{x['유통기한']}] {x['품명']} | {x['브랜드']} | 재고:{x.get('재고량','?')}", axis=1
            )
            # 드롭다운 선택
            selected_label = st.selectbox("실제 출고할 재고 선택 (유통기한 임박순)", selection_df['label'].tolist())
            selected_row = selection_df[selection_df['label'] == selected_label].iloc[0]
        else:
            st.warning("해당 품명의 재고가 없습니다.")

    # 출고 정보 입력 폼
    with st.form("outbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            out_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["신상명", "관리자", "기타"])
            client = st.text_input("거래처")
        with col2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부")
            comments = st.text_input("변경사항 (비고)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                # 에이젯광주 출고증 시트 형식 (L열: 이체여부, M열: 변경사항)
                new_row = [
                    str(out_date),       # A
                    manager,             # B
                    client,              # C
                    selected_row['품명'], # D
                    selected_row['브랜드'], # E
                    amount,              # F
                    selected_row['유통기한'], # G
                    "", "", "", "",      # H, I, J, K
                    "이체" if is_transfer else "", # L열
                    comments             # M열
                ]
                try:
                    save_outbound(new_row)
                    st.success(f"✅ {selected_row['품명']} 등록 완료!")
                    st.cache_data.clear() # 등록 후 재고 갱신을 위해 캐시 삭제
                except Exception as e:
                    st.error(f"저장 실패: {e}")
            else:
                st.error("품목 선택과 거래처 입력은 필수입니다.")
