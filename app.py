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
@st.cache_data(ttl=300) # 5분마다 갱신
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = df.columns.str.strip() # 공백 제거
    
    # 소비기한/유통기한 컬럼 자동 찾기
    e_col = next((c for c in ['소비기한', '유통기한', '만료일'] if c in df.columns), df.columns[0])
    p_col = next((c for c in ['품명', '품목', '상품명'] if c in df.columns), df.columns[0])
    b_col = next((c for c in ['브랜드', '메이커'] if c in df.columns), df.columns[1])

    # 날짜 정렬용 임시 컬럼
    df['date_sort'] = pd.to_datetime(df[e_col], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
    
    # 이름 통일
    df = df.rename(columns={p_col: '품명', b_col: '브랜드', e_col: '소비기한'})
    return df

# --- 출고 저장 함수 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 로그인 (AZ: 5835 / AZS: 0983) ---
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
        else: st.error("로그인 정보가 틀렸습니다.")
    st.stop()

# --- 메인 로직 ---
df = load_inventory()

st.title("📦 에이젯 실시간 재고 현황")
st.dataframe(df.drop(columns=['date_sort']), use_container_width=True, hide_index=True)

# --- 출고 등록 (AZS 전용) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록 (선입선출)")
    
    # 1. 품목 검색 (여기서 검색어를 쳐야 아래 드롭다운에 재고가 뜹니다!)
    item_query = st.text_input("출고할 품목 검색 (예: 삼겹양지)", placeholder="품명을 입력하면 아래 드롭다운에 목록이 나타납니다.")
    
    selected_row = None
    if item_query:
        # 대소문자 구분 없이 검색어 포함된 재고 필터링 + 소비기한순 정렬
        selection = df[df['품명'].str.contains(item_query, na=False, case=False)].sort_values('date_sort')
        
        if not selection.empty:
            # 드롭다운에 표시할 텍스트 구성
            selection['label'] = selection.apply(lambda x: f"[{x['소비기한']}] {x['품명']} | {x['브랜드']}", axis=1)
            target_label = st.selectbox("재고 선택 (소비기한 임박순)", selection['label'].tolist())
            selected_row = selection[selection['label'] == target_label].iloc[0]
        else:
            st.warning("⚠️ 해당 품명의 재고가 없습니다. 검색어를 다시 확인해 주세요.")
    else:
        st.info("💡 위 칸에 품명을 입력하시면 선택 가능한 재고 목록이 드롭다운으로 나타납니다.")

    # 2. 출고 정보 입력 폼
    with st.form("outbound_form", clear_on_submit=True):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            o_date = st.date_input("출고일", datetime.now())
            # 요청하신 담당자 순서 반영
            manager = st.selectbox("담당자", ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"])
            client = st.text_input("거래처")
        with f_col2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부 (L열 기록)")
            comments = st.text_input("변경사항 (M열 기록)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                row = [
                    str(o_date), manager, client, 
                    selected_row['품명'], selected_row['브랜드'], 
                    amount, selected_row['소비기한'],
                    "", "", "", "", # H~K열
                    "이체" if is_transfer else "", # L열
                    comments # M열
                ]
                try:
                    save_outbound(row)
                    st.success(f"✅ {selected_row['품명']} 등록 완료!")
                    st.cache_data.clear() # 재고 갱신
                except Exception as e: st.error(f"저장 실패: {e}")
            else:
                st.error("⚠️ 품목 선택과 거래처 입력은 필수입니다.")
