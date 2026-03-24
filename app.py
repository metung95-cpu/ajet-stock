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

# --- 데이터 로딩 ---
@st.cache_data(ttl=600)
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    # 유통기한 정렬을 위해 날짜 형식 변환 (실패 시 나중 날짜로 처리)
    df['유통기한_dt'] = pd.to_datetime(df['유통기한'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
    return df

# --- 출고 데이터 저장 함수 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    # '에이젯광주 출고증' 독스 열기
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0) # 첫 번째 시트 선택
    sheet.append_row(data_list)

# --- 로그인 시스템 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 에이젯 재고관리 로그인")
    user_id = st.text_input("아이디 (AZ 또는 AZS)")
    password = st.text_input("비밀번호", type="password") 
    if st.button("로그인"):
        if user_id == "AZ" and password == "5835":
            st.session_state.logged_in = True
            st.session_state.user_role = "AZ"
            st.rerun()
        elif user_id == "AZS" and password == "0983":
            st.session_state.logged_in = True
            st.session_state.user_role = "AZS"
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 틀렸습니다.")
    st.stop()

st.sidebar.write(f"👤 접속: {st.session_state.user_role}")
if st.sidebar.button("로그아웃"):
    st.session_state.logged_in = False
    st.rerun()

df = load_inventory()

st.title("📦 에이젯 실시간 재고 현황")

# --- 상단 재고 조회 필터 ---
col1, col2 = st.columns(2)
with col1: search_name = st.text_input("품명 검색 (조회용)", "")
with col2: search_brand = st.text_input("브랜드 검색 (조회용)", "")

view_df = df.copy()
if search_name: view_df = view_df[view_df['품명'].str.contains(search_name, na=False)]
if search_brand: view_df = view_df[view_df['브랜드'].str.contains(search_brand, na=False)]

if st.session_state.user_role == "AZS":
    if '창고' in view_df.columns:
        view_df = view_df[view_df['창고'] != '본점']

st.dataframe(view_df.drop(columns=['유통기한_dt']), use_container_width=True, hide_index=True)

# --- 출고 등록 기능 (AZS 전용) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    # 1. 품목 검색 및 유통기한순 정렬
    item_search = st.text_input("출고할 품목 검색 (예: 삼겹양지)", "")
    
    if item_search:
        # 검색어 포함된 재고 필터링 및 유통기한순 정렬
        selection_df = df[df['품명'].str.contains(item_search, na=False)].sort_values(by='유통기한_dt')
        
        if not selection_df.empty:
            # 드롭다운에 표시할 텍스트 생성 (품명 | 브랜드 | 유통기한 | 재고량)
            selection_df['display'] = selection_df.apply(
                lambda x: f"{x['품명']} | {x['브랜드']} | {x['유통기한']} | 재고:{x.get('재고량', '0')}", axis=1
            )
            selected_item_str = st.selectbox("출고 품목 선택 (유통기한 임박순)", selection_df['display'].tolist())
            selected_row = selection_df[selection_df['display'] == selected_item_str].iloc[0]
        else:
            st.warning("검색된 재고가 없습니다.")
            selected_row = None
    else:
        st.info("위 칸에 품목명을 입력하면 선택 가능한 목록이 나옵니다.")
        selected_row = None

    with st.form("outbound_form"):
        col_form1, col_form2 = st.columns(2)
        with col_form1:
            out_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["신상명", "관리자", "기타"])
            client = st.text_input("거래처")
        with col_form2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부 (체크 시 L열에 '이체' 기록)")
            comments = st.text_area("변경사항 (M열 기록)", placeholder="기타 특이사항 입력")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                # 시트에 들어갈 행 데이터 구성 (A~K열은 기존 형식 유지, L, M열 추가)
                # 시트 구조에 따라 순서를 맞춰주세요. (예: 일자, 담당, 거래처, 품명, 브랜드, 수량, ..., 이체여부, 변경사항)
                new_row = [
                    str(out_date),       # A
                    manager,             # B
                    client,              # C
                    selected_row['품명'], # D
                    selected_row['브랜드'], # E
                    amount,              # F
                    selected_row['유통기한'], # G
                    "", "", "", "",      # H, I, J, K (빈칸 처리)
                    "이체" if is_transfer else "", # L열: 이체여부
                    comments             # M열: 변경사항
                ]
                
                try:
                    save_outbound(new_row)
                    st.success(f"✅ {selected_row['품명']} ({amount}개) 출고 등록 완료!")
                except Exception as e:
                    st.error(f"❌ 저장 실패: {e}")
            else:
                st.error("품목 선택과 거래처 입력은 필수입니다.")
