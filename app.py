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

# --- 2. 데이터 로딩 (인덱스 기반 매핑) ---
@st.cache_data(ttl=60)
def load_inventory():
    try:
        gc = get_gspread_client()
        doc = gc.open('에이젯광주 운영독스')
        worksheet = doc.worksheet('raw_운영부재고')
        all_data = worksheet.get_all_values()
        
        if len(all_data) <= 1: return pd.DataFrame()

        # 원본 헤더 무시하고 상명님 시트 위치(A, B, D, E, F)로 직접 매핑
        rows = all_data[1:]
        processed = []
        for r in rows:
            # 칸이 부족할 경우 대비해 최소 6열(F열)까지 있는지 확인
            if len(r) < 6: continue
            
            warehouse = r[4].strip() # E열: 창고명
            item_name = r[0].strip() # A열: 품명
            brand = r[1].strip()     # B열: 브랜드-등급-est
            qty = r[3].strip()       # D열: 재고수량
            expiry = r[5].strip()    # F열: 소비기한
            
            # 날짜 축소 (2027.02.16 -> 27.02.16)
            short_exp = expiry[2:] if expiry.startswith("20") else expiry
            
            # 본점 정렬용 (본점이면 1, 아니면 0)
            is_bonjum = 1 if "본점" in warehouse else 0
            
            processed.append({
                "품목": item_name,
                "브랜드": brand,
                "재고": qty,
                "창고": warehouse,
                "소비기한": short_exp,
                "_full_expiry": expiry,
                "_is_bonjum": is_bonjum,
                "_date_sort": pd.to_datetime(expiry, errors='coerce').fillna(pd.Timestamp('2099-12-31'))
            })
            
        return pd.DataFrame(processed)
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

# --- 5. 실시간 재고 현황 (품목-브랜드-재고-창고-소비기한 순서) ---
st.title("📦 에이젯 실시간 재고 현황")

if not df.empty:
    col1, col2 = st.columns(2)
    with col1: f_name = st.text_input("🔍 품명 검색", "")
    with col2: f_brand = st.text_input("🔍 브랜드 검색", "")

    v_df = df.copy()
    if f_name: v_df = v_df[v_df['품목'].str.contains(f_name, na=False, case=False)]
    if f_brand: v_df = v_df[v_df['브랜드'].str.contains(f_brand, na=False, case=False)]

    # [중요] 정렬: 본점 여부(0->1) -> 브랜드 -> 소비기한 순
    v_df = v_df.sort_values(by=['_is_bonjum', '브랜드', '_date_sort'])
    
    # [중요] 상명님이 요청하신 순서대로 열 배치
    display_cols = ['품목', '브랜드', '재고', '창고', '소비기한']
    st.dataframe(v_df[display_cols], use_container_width=True, hide_index=True)

# --- 6. 출고 등록 (본점 완전 제외) ---
if st.session_state.user_role == "AZS" and not df.empty:
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    item_query = st.text_input("출고할 품목 검색", key="out_search")
    
    selected_row = None
    if item_query:
        # [핵심] 출고 등록에서는 본점(_is_bonjum == 1)을 아예 제거
        sel = df[(df['품목'].str.contains(item_query, na=False, case=False)) & (df['_is_bonjum'] == 0)]
        sel = sel.sort_values(by=['브랜드', '_date_sort'])
        
        if not sel.empty:
            # 포맷: 소비기한 / 품목 / 브랜드 / 재고 / 창고
            sel['label'] = sel.apply(lambda x: f"{x['소비기한']} / {x['품목']} / {x['브랜드']} / {x['재고']} / {x['창고']}", axis=1)
            target = st.selectbox("재고 선택 (본점 제외됨)", sel['label'].tolist())
            selected_row = sel[sel['label'] == target].iloc[0]
        else:
            st.warning("선택 가능한 재고가 없습니다. (본점 외 재고 없음)")

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
                # 시트 저장 (F열 원본 날짜 사용)
                row = [str(o_date), manager, client, selected_row['품목'], selected_row['브랜드'], amt, selected_row['_full_expiry'], "", "", "", "", "이체" if is_trans else "", memo]
                try:
                    save_outbound(row)
                    st.success("✅ 등록 성공!")
                    st.cache_data.clear() # 캐시 즉시 삭제하여 데이터 갱신
                except Exception as e: st.error(f"저장 실패: {e}")
