import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

# 1. 페이지 기본 설정
st.set_page_config(page_title="에이젯 재고관리", layout="wide")

# 2. 구글 인증 함수 (Secrets의 gcp_service_account 사용)
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        # 내 컴퓨터에서 테스트할 때용
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
    return gspread.authorize(credentials)

# 3. 재고 데이터 불러오기 (소비기한 기준 정렬)
@st.cache_data(ttl=600)
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    
    # 컬럼명 앞뒤 공백 제거 (에러 방지)
    df.columns = df.columns.str.strip()
    
    # '소비기한' 컬럼을 날짜 형식으로 변환해서 정렬용 데이터 만들기
    # 이름이 '유통기한'일 경우를 대비해 유연하게 대처
    e_col = '소비기한' if '소비기한' in df.columns else ('유통기한' if '유통기한' in df.columns else df.columns[0])
    df['소비기한_dt'] = pd.to_datetime(df[e_col], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
    
    # 내부 표시용 이름 통일
    df = df.rename(columns={e_col: '소비기한'})
    return df

# 4. 출고 내역 저장 함수 (에이젯광주 출고증 L, M열 반영)
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0) # 첫 번째 시트에 저장
    sheet.append_row(data_list)

# 5. 로그인 시스템 (AZ: 5835 / AZS: 0983)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 에이젯 재고관리 로그인")
    u_id = st.text_input("아이디 (AZ 또는 AZS)")
    u_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        if u_id == "AZ" and u_pw == "5835":
            st.session_state.logged_in = True
            st.session_state.user_role = "AZ"
            st.rerun()
        elif u_id == "AZS" and u_pw == "0983":
            st.session_state.logged_in = True
            st.session_state.user_role = "AZS"
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 틀렸습니다.")
    st.stop()

# --- 메인 화면 시작 ---
df = load_inventory()

st.sidebar.write(f"👤 접속: {st.session_state.user_role}")
if st.sidebar.button("로그아웃"):
    st.session_state.logged_in = False
    st.rerun()

st.title("📦 에이젯 실시간 재고 현황")

# 재고 조회 필터
col1, col2 = st.columns(2)
with col1: s_name = st.text_input("품명 검색", "")
with col2: s_brand = st.text_input("브랜드 검색", "")

view_df = df.copy()
if s_name: view_df = view_df[view_df['품명'].str.contains(s_name, na=False)]
if s_brand: view_df = view_df[view_df['브랜드'].str.contains(s_brand, na=False)]

# AZS는 본점 데이터 숨기기
if st.session_state.user_role == "AZS":
    if '창고' in view_df.columns:
        view_df = view_df[view_df['창고'] != '본점']

st.dataframe(view_df.drop(columns=['소비기한_dt']), use_container_width=True, hide_index=True)

# --- 6. 출고 등록 (AZS 전용 기능) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록 (선입선출)")
    
    # 품목 검색창 (여기 검색 결과로 드롭다운을 만듭니다)
    item_query = st.text_input("출고할 품목 검색 (예: 삼겹양지)", "")
    
    selected_row = None
    if item_query:
        # 검색어가 포함된 재고만 골라 소비기한 임박순으로 정렬
        selection = df[df['품명'].str.contains(item_query, na=False)].sort_values(by='소비기한_dt')
        
        if not selection.empty:
            # 드롭다운에 표시할 텍스트 (소비기한 | 품명 | 브랜드)
            selection['label'] = selection.apply(lambda x: f"[{x['소비기한']}] {x['품명']} | {x['브랜드']}", axis=1)
            target_label = st.selectbox("정확한 재고 선택 (소비기한 임박순)", selection['label'].tolist())
            selected_row = selection[selection['label'] == target_label].iloc[0]
        else:
            st.warning("해당 품명의 재고가 없습니다.")

    # 출고 정보 입력 폼
    with st.form("outbound_form", clear_on_submit=True):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            o_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["신상명", "관리자", "기타"])
            client = st.text_input("거래처")
        with f_col2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부 (체크 시 L열에 '이체' 기록)")
            comments = st.text_input("변경사항 (M열 기록)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                # 시트 한 줄 데이터 (A~M열 순서 맞춤)
                new_row = [
                    str(o_date),            # A: 일자
                    manager,                # B: 담당자
                    client,                 # C: 거래처
                    selected_row['품명'],    # D: 품명
                    selected_row['브랜드'],  # E: 브랜드
                    amount,                 # F: 수량
                    selected_row['소비기한'], # G: 소비기한
                    "", "", "", "",         # H, I, J, K: 공백
                    "이체" if is_transfer else "", # L: 이체여부
                    comments                # M: 변경사항
                ]
                try:
                    save_outbound(new_row)
                    st.success(f"✅ {selected_row['품명']} 출고 등록 완료!")
                    st.cache_data.clear() # 재고량 변동 반영을 위해 캐시 초기화
                except Exception as e:
                    st.error(f"❌ 저장 중 오류 발생: {e}")
            else:
                st.error("품목 선택과 거래처 입력은 필수입니다.")
