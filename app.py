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

# --- 2. 데이터 로딩 (가장 확실한 인덱스 번호 방식) ---
@st.cache_data(ttl=60)
def load_inventory():
    try:
        gc = get_gspread_client()
        doc = gc.open('에이젯광주 운영독스')
        worksheet = doc.worksheet('raw_운영부재고')
        all_data = worksheet.get_all_values()
        
        if len(all_data) <= 1: return pd.DataFrame()

        # 헤더와 데이터 분리
        rows = all_data[1:]
        
        processed_data = []
        for r in rows:
            # 시트 사진 기준: A(0):품명, B(1):브랜드, D(3):재고수량, E(4):창고명, F(5):소비기한
            # 칸이 부족한 경우를 대비해 예외처리
            try:
                warehouse = r[4].strip() if len(r) > 4 else ""
                
                # [핵심] '본점' 데이터는 아예 추가하지 않음
                if warehouse == "본점" or not warehouse:
                    continue
                
                item_name = r[0].strip() if len(r) > 0 else ""
                brand = r[1].strip() if len(r) > 1 else ""
                qty = r[3].strip() if len(r) > 3 else "0"
                expiry = r[5].strip() if len(r) > 5 else ""
                
                # 날짜 축소 (2027.02.16 -> 27.02.16)
                short_exp = expiry[2:] if expiry.startswith("20") else expiry
                
                # 정렬용 날짜 객체
                try:
                    dt_sort = pd.to_datetime(expiry.replace('.', '-'))
                except:
                    dt_sort = pd.Timestamp('2099-12-31')

                processed_data.append({
                    "소비기한": short_exp,
                    "품목": item_name,
                    "브랜드": brand,
                    "재고": qty,
                    "창고": warehouse,
                    "full_expiry": expiry,
                    "date_sort": dt_sort
                })
            except:
                continue
                
        return pd.DataFrame(processed_data)
    except Exception as e:
        st.error(f"데이터 연결 오류: {e}")
        return pd.DataFrame()

# --- 3. 출고 저장 함수 ---
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

# --- 5. 데이터 불러오기 ---
df = load_inventory()

st.title("📦 에이젯 실시간 재고 현황")

if df.empty:
    st.warning("표시할 재고가 없습니다. 시트의 창고명이 '본점'이 아닌 데이터가 있는지 확인해주세요.")
else:
    # --- 상단 필터 (중복 필터링) ---
    col1, col2 = st.columns(2)
    with col1: f_name = st.text_input("🔍 품명 검색", "")
    with col2: f_brand = st.text_input("🔍 브랜드 검색", "")

    v_df = df.copy()
    if f_name: v_df = v_df[v_df['품목'].str.contains(f_name, na=False, case=False)]
    if f_brand: v_df = v_df[v_df['브랜드'].str.contains(f_brand, na=False, case=False)]

    # 브랜드별 묶고 소비기한 순 정렬
    v_df = v_df.sort_values(by=['브랜드', 'date_sort'])
    
    st.dataframe(v_df[['소비기한', '품목', '브랜드', '재고', '창고']], use_container_width=True, hide_index=True)

# --- 6. 출고 등록 (AZS 전용) ---
if st.session_state.user_role == "AZS" and not df.empty:
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    # [검색창]
    item_query = st.text_input("출고할 품목 검색 (예: 삼겹)", key="out_search")
    
    selected_row = None
    if item_query:
        # 검색 필터링 및 정렬
        sel = df[df['품목'].str.contains(item_query, na=False, case=False)].sort_values(by=['브랜드', 'date_sort'])
        
        if not sel.empty:
            # [요청 포맷] 26.11.20 / 품목 / 브랜드 / 수량 / 창고
            sel['label'] = sel.apply(lambda x: f"{x['소비기한']} / {x['품목']} / {x['브랜드']} / {x['재고']} / {x['창고']}", axis=1)
            target = st.selectbox("재고 선택", sel['label'].tolist())
            selected_row = sel[sel['label'] == target].iloc[0]
        else:
            st.warning("검색된 재고가 없습니다.")

    with st.form("outbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            o_date = st.date_input("출고일", datetime.now())
            # [담당자 순서 고정]
            m_list = ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"]
            manager = st.selectbox("담당자", m_list)
            client = st.text_input("거래처")
        with c2:
            amt = st.number_input("수량", min_value=1, step=1)
            is_trans = st.checkbox("이체 여부 (체크 시 L열 기록)")
            memo = st.text_input("변경사항 (M열 기록)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                # 시트 저장 (A~M열 순서)
                row = [
                    str(o_date), manager, client, 
                    selected_row['품목'], selected_row['브랜드'], 
                    amt, selected_row['full_expiry'], 
                    "", "", "", "", 
                    "이체" if is_trans else "", 
                    memo
                ]
                try:
                    save_outbound(row)
                    st.success("✅ 등록 완료!")
                    st.cache_data.clear() # 재고 새로고침
                except Exception as e:
                    st.error(f"저장 실패: {e}")
            else:
                st.error("품목 선택과 거래처 입력은 필수입니다.")
