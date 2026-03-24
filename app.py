import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="에이젯 재고관리", layout="wide")

# --- 1. 구글 인증 ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
    return gspread.authorize(credentials)

# --- 2. 데이터 로딩 (전체 열 유지 + 정렬 로직) ---
@st.cache_data(ttl=60)
def load_inventory():
    try:
        gc = get_gspread_client()
        doc = gc.open('에이젯광주 운영독스')
        worksheet = doc.worksheet('raw_운영부재고')
        all_data = worksheet.get_all_values()
        
        if len(all_data) <= 1: return pd.DataFrame()

        # 원본 헤더와 데이터 가져오기
        headers = [h.strip() for h in all_data[0]]
        df = pd.DataFrame(all_data[1:], columns=headers)
        
        # [열 위치 기반 핵심 데이터 추출]
        # A(0):품명, B(1):브랜드, D(3):재고수량, E(4):창고명, F(5):소비기한
        df['_품명'] = df.iloc[:, 0].str.strip()
        df['_브랜드'] = df.iloc[:, 1].str.strip()
        df['_재고'] = df.iloc[:, 3].str.strip()
        df['_창고'] = df.iloc[:, 4].str.strip()
        df['_소비'] = df.iloc[:, 5].str.strip()
        
        # [날짜 가공]
        df['_소비_short'] = df['_소비'].apply(lambda x: x[2:] if str(x).startswith("20") else x)
        df['_date_sort'] = pd.to_datetime(df['_소비'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
        
        # [본점 정렬용] 본점이면 1, 아니면 0
        df['_is_bonjum'] = df['_창고'].apply(lambda x: 1 if "본점" in str(x) else 0)
        
        return df
    except Exception as e:
        st.error(f"데이터 연결 오류: {e}")
        return pd.DataFrame()

# --- 3. 출고 저장 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 4. 로그인 시스템 ---
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

df = load_inventory()

# --- 5. 실시간 재고 현황 (표: 본점 최하단) ---
st.title("📦 에이젯 실시간 재고 현황")

if not df.empty:
    col1, col2 = st.columns(2)
    with col1: f_name = st.text_input("🔍 품명 검색", "")
    with col2: f_brand = st.text_input("🔍 브랜드 검색", "")

    v_df = df.copy()
    if f_name: v_df = v_df[v_df['_품명'].str.contains(f_name, na=False, case=False)]
    if f_brand: v_df = v_df[v_df['_브랜드'].str.contains(f_brand, na=False, case=False)]

    # [표 정렬] 본점 물량을 무조건 맨 아래로 (0: 타창고, 1: 본점)
    v_df = v_df.sort_values(by=['_is_bonjum', '_브랜드', '_date_sort'])
    
    # 원본 열만 노출
    original_cols = [c for c in v_df.columns if not str(c).startswith('_')]
    st.dataframe(v_df[original_cols], use_container_width=True, hide_index=True)

# --- 6. 출고 등록 (드롭다운: 본점 완전 제거) ---
if st.session_state.user_role == "AZS" and not df.empty:
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    item_query = st.text_input("출고할 품목 검색", key="out_search")
    
    selected_row = None
    if item_query:
        # [핵심] 검색어 포함 + '본점' 재고는 아예 제외
        sel = df[(df['_품명'].str.contains(item_query, na=False, case=False)) & (df['_is_bonjum'] == 0)]
        sel = sel.sort_values(by=['_브랜드', '_date_sort'])
        
        if not sel.empty:
            # 드롭다운 형식: 소비기한 / 품목 / 브랜드 / 수량 / 창고
            sel['label'] = sel.apply(lambda x: f"{x['_소비_short']} / {x['_품명']} / {x['_브랜드']} / {x['_재고']} / {x['_창고']}", axis=1)
            target = st.selectbox("재고 선택 (본점 물량 제외됨)", sel['label'].tolist())
            selected_row = sel[sel['label'] == target].iloc[0]
        else:
            st.warning("선택 가능한 재고가 없습니다. (본점 재고만 있거나 검색 결과가 없음)")

    with st.form("outbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            o_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"])
            client = st.text_input("거래처")
        with c2:
            amt = st.number_input("수량", min_value=1, step=1)
            is_trans = st.checkbox("이체 여부 (L열)")
            memo = st.text_input("변경사항 (M열)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                # 시트 저장 (F열 데이터는 원본 소비기한 사용)
                save_data = [
                    str(o_date), manager, client, 
                    selected_row['_품목'] if '_품목' in selected_row else selected_row.iloc[0], 
                    selected_row['_브랜드'], amt, selected_row['_소비'], 
                    "", "", "", "", 
                    "이체" if is_trans else "", 
                    memo
                ]
                try:
                    save_outbound(save_data)
                    st.success("✅ 등록 완료!")
                    st.cache_data.clear()
                except Exception as e: st.error(f"저장 실패: {e}")
            else:
                st.error("입력 정보를 다시 확인해주세요.")
