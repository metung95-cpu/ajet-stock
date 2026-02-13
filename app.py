import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import extra_streamlit_components as stx

# ------------------------------------------------------------------
# 1. 기본 설정 및 스타일
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 재고관리 Pro", page_icon="🥩", layout="wide")

st.markdown("""
    <style>
        div[data-baseweb="select"] > div { white-space: normal !important; height: auto !important; min-height: 60px; }
        ul[role="listbox"] li span { white-space: normal !important; word-break: break-all !important; display: block !important; line-height: 1.6 !important; }
        .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

USERS = {"AZ": "5835", "AZS": "0983"}
MANAGERS = ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"]
COOKIE_NAME = "ajet_real_final_v6" 

# ------------------------------------------------------------------
# 2. 쿠키 및 세션 관리
# ------------------------------------------------------------------
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()
time.sleep(0.5)

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None

cookie_val = cookie_manager.get(COOKIE_NAME)
if cookie_val:
    st.session_state['logged_in'] = True
    st.session_state['user_id'] = cookie_val

# ------------------------------------------------------------------
# 3. 데이터 로드 및 전처리 (안전 장치 포함)
# ------------------------------------------------------------------
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def load_inventory_data():
    try:
        client = get_gspread_client()
        sh = client.open('에이젯광주 운영독스').worksheet('raw_운영부재고')
        df = pd.DataFrame(sh.get_all_records())
        
        # 컬럼명 표준화 (오류 방지)
        df.rename(columns={'B/L NO':'BL넘버','식별번호':'BL넘버','B/L NO,식별번호':'BL넘버','브랜드-등급-est':'브랜드'}, inplace=True)
        
        # 데이터 정제: 모든 셀을 문자열로 변환 후 공백 제거 (NaN 방지)
        df = df.fillna("").astype(str).apply(lambda x: x.str.strip())
        return df
    except Exception as e:
        st.error(f"❌ 재고 데이터 로드 실패: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_price_data():
    try:
        client = get_gspread_client()
        # 시세 시트 ID 사용
        sh = client.open_by_key('1UkHP0AEgMtkvxOgmfEuR2ufcmJZ_Offyx_so9_4c2VQ').worksheet('시세')
        df = pd.DataFrame(sh.get_all_records())
        
        # 필수 컬럼 체크
        required_cols = ['품명', '브랜드', '단가']
        if not all(col in df.columns for col in required_cols):
            st.warning("⚠️ 시세 시트에 '품명', '브랜드', '단가' 컬럼이 정확히 있는지 확인해주세요.")
            return pd.DataFrame()
            
        # 데이터 정제 (숫자 변환 로직 강화)
        df = df.fillna("").astype(str).apply(lambda x: x.str.strip())
        
        # '단가' 컬럼을 숫자로 강제 변환 (콤마, 원, 공백 제거)
        def clean_price(val):
            try:
                # 숫자 외의 문자 제거
                clean_str = ''.join(filter(str.isdigit, str(val)))
                return int(clean_str) if clean_str else 0
            except:
                return 0
        
        df['단가_숫자'] = df['단가'].apply(clean_price)
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error("❌ '시세' 시트를 찾을 수 없습니다. 시트 이름을 확인하세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 시세 데이터 로드 중 오류: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 4. 로그인 로직
# ------------------------------------------------------------------
def login_check(username, password):
    if username in USERS and USERS[username] == password:
        st.session_state['logged_in'] = True
        st.session_state['user_id'] = username
        expires = datetime.now() + timedelta(days=7)
        cookie_manager.set(COOKIE_NAME, username, expires_at=expires)
        st.success("✅ 로그인 성공!")
        time.sleep(1)
        st.rerun()
    else:
        st.error("아이디 또는 비밀번호 확인")

def logout():
    cookie_manager.delete(COOKIE_NAME)
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.rerun()

if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    with st.form("login_form"):
        i_id = st.text_input("아이디")
        i_pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인", type="primary", use_container_width=True):
            login_check(i_id.strip().upper(), i_pw.strip())
    st.stop()

# ------------------------------------------------------------------
# 5. 메인 대시보드
# ------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 **{st.session_state['user_id']}**님")
    if st.button("로그아웃"):
        logout()

st.title("🥩 에이젯광주 통합 관리 시스템")

# 데이터 로딩
df_inventory = load_inventory_data()
df_price = load_price_data()

if not df_inventory.empty:
    # --- [검색 섹션] ---
    c1, c2 = st.columns(2)
    s_item = c1.text_input("🔍 품명 검색", placeholder="예: 등심")
    s_brand = c2.text_input("🏢 브랜드 검색", placeholder="예: 스위프트")
    
    # --- [시세 정보 표시 로직 (안전함)] ---
    if not df_price.empty and (s_item or s_brand):
        p_filter = df_price.copy()
        if s_item: 
            p_filter = p_filter[p_filter['품명'].str.contains(s_item, na=False)]
        if s_brand: 
            p_filter = p_filter[p_filter['브랜드'].str.contains(s_brand, na=False, case=False)]
        
        if not p_filter.empty:
            with st.expander("💰 검색 품목 시세 정보 (클릭하여 펼치기)", expanded=True):
                st.dataframe(
                    p_filter[['품명', '브랜드', '단가']], 
                    use_container_width=True, 
                    hide_index=True
                )
        else:
            if s_item or s_brand:
                st.caption("ℹ️ 검색 조건에 맞는 시세 정보가 없습니다.")

    # --- [재고 필터링] ---
    f_df = df_inventory.copy()
    if s_item: f_df = f_df[f_df['품명'].str.contains(s_item, na=False)]
    if s_brand: f_df = f_df[f_df['브랜드'].str.contains(s_brand, na=False, case=False)]
    
    current_user = st.session_state['user_id']
    
    # 사용자별 컬럼 설정
    if current_user == "AZS":
        f_df = f_df[~f_df['창고명'].str.contains("본점", na=False)]
        disp_cols = ['품명', '브랜드', '재고수량', 'BL넘버', '창고명', '소비기한']
    else:
        disp_cols = ['품명', '브랜드', '재고수량', '창고명', '소비기한']
    
    # 컬럼이 실제 존재하는지 확인 후 표시 (오류 방지)
    valid_cols = [c for c in disp_cols if c in f_df.columns]
    st.dataframe(f_df[valid_cols], use_container_width=True, hide_index=True)

    # --- [출고 등록 섹션] ---
    if current_user == "AZS":
        st.divider()
        st.header("🚚 출고 등록")
        
        sc1, sc2 = st.columns(2)
        r_item = sc1.text_input("🔍 출고 품목 검색", key="r_i")
        r_brand = sc2.text_input("🏢 출고 브랜드 검색", key="r_b")
        
        t_df = f_df.copy().reset_index(drop=True)
        if r_item: t_df = t_df[t_df['품명'].str.contains(r_item, na=False)]
        if r_brand: t_df = t_df[t_df['브랜드'].str.contains(r_brand, na=False, case=False)]
        
        if '소비기한' in t_df.columns:
            t_df = t_df.sort_values(by='소비기한', ascending=True)
        
        if not t_df.empty:
            # 옵션 생성 (가독성 향상)
            opts = t_df.apply(lambda x: f"[{x.get('창고명','미지정')}] {x['품명']} / {x['브랜드']} (재고: {x.get('재고수량','0')}) [기한: {x.get('소비기한','')}]".strip(), axis=1)
            sel_idx = st.selectbox("출고 품목 선택 (소비기한 임박순)", opts.index, format_func=lambda i: opts[i])
            row = t_df.loc[sel_idx]

            # --- [재고 수량 파싱 안전 로직] ---
            try:
                stock_val = str(row.get('재고수량', '0')).replace(',', '')
                available_stock = float(stock_val) if stock_val else 0.0
            except:
                available_stock = 0.0

            # --- [단가 자동 매칭 로직 (Pro)] ---
            suggested_price = 0
            price_found = False
            
            if not df_price.empty:
                # 정확도를 위해 품명과 브랜드가 모두 포함된 경우를 찾음
                match_row = df_price[
                    (df_price['품명'] == row['품명']) & 
                    (df_price['브랜드'] == row['브랜드'])
                ]
                
                # 정확한 매칭이 없으면 '품명'만이라도 일치하는 첫 번째 항목 시도
                if match_row.empty:
                    match_row = df_price[df_price['품명'] == row['품명']]
                
                if not match_row.empty:
                    suggested_price = int(match_row.iloc[0]['단가_숫자'])
                    price_found = True

            # --- [출고 폼] ---
            with st.form("out_form"):
                f1, f2, f3 = st.columns(3)
                out_date = f1.date_input("출고일", datetime.now())
                manager = f1.selectbox("담당자", MANAGERS)
                client_name = f1.text_input("거래처")
                
                qty = f3.number_input("수량 (kg/box)", min_value=1.0, step=1.0, value=1.0)
                
                # 단가 입력 필드 (자동 매칭된 값 기본 적용)
                price = f3.number_input(
                    "단가 (원)", 
                    min_value=0, 
                    step=100, 
                    value=suggested_price,
                    help="시세 시트에서 자동으로 가져온 가격입니다." if price_found else "일치하는 시세 정보가 없어 0원으로 표시됩니다."
                )
                
                is_trans = f3.checkbox("이체 여부", value=False)
                
                if price_found:
                    f3.caption(f"✅ 시세 데이터 연동됨: {suggested_price:,}원")
                
                if qty > available_stock:
                    st.error(f"🚨 재고 부족! (현재고: {available_stock})")

                # 제출 로직
                if st.form_submit_button("출고 등록하기", type="primary"):
                    if qty > available_stock:
                        st.error("❌ 재고 부족으로 출고할 수 없습니다.")
                    elif not client_name:
                        st.error("❌ 거래처 이름을 입력해주세요.")
                    else:
                        try:
                            client = get_gspread_client()
                            out_sh = client.open_by_key('1xdRllSZ0QTS_h8-HNbs0RqFja9PKnklYon7xrKDHTbo').worksheet('출고증')
                            
                            target_date = f"{out_date.month}. {out_date.day}"
                            vals = out_sh.get_all_values()
                            
                            # 빈 행 찾기 로직
                            target_idx = -1
                            for i, r in enumerate(vals, 1):
                                if len(r) > 2 and str(r[2]).strip() == target_date:
                                    # 거래처 컬럼(D열, 인덱스3)이 비어있는지 확인
                                    if len(r) <= 3 or str(r[3]).strip() == "":
                                        target_idx = i
                                        break
                            
                            if target_idx != -1:
                                data = [
                                    str(manager), 
                                    str(client_name), 
                                    str(row['품명']), 
                                    str(row['브랜드']), 
                                    str(row.get('BL넘버','-')), 
                                    int(qty), 
                                    str(row.get('창고명','')), 
                                    int(price), 
                                    "이체" if is_trans else ""
                                ]
                                # D열(4번째)부터 L열(12번째)까지 업데이트
                                out_sh.update(range_name=f"D{target_idx}:L{target_idx}", values=[data], value_input_option='USER_ENTERED')
                                st.success("✅ 출고 등록이 완료되었습니다!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ '{target_date}' 날짜에 입력 가능한 빈 행을 찾을 수 없습니다.")
                        except Exception as e:
                            st.error(f"❌ 데이터 전송 중 오류 발생: {e}")
        else:
            st.info("👆 위에서 품목을 검색하시면 출고 등록이 가능합니다.")
