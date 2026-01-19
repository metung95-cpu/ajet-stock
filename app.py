import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ------------------------------------------------------------------
# 1. 기본 설정 및 로그인
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 재고관리", page_icon="🥩", layout="wide")

# 사용자 계정 설정
USERS = {
    "AZ": "5835",   # 관리자 (조회 전용)
    "AZS": "0983"   # 영업/물류 (조회 + 출고 등록 가능)
}

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

def login_check(username, password):
    if username in USERS and USERS[username] == password:
        st.session_state['logged_in'] = True
        st.session_state['user_id'] = username
        st.rerun()
    else:
        st.error("아이디 또는 비밀번호를 확인하세요.")

if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    input_id = st.text_input("아이디")
    input_pw = st.text_input("비밀번호", type="password")
    
    # 로그인 버튼 (대소문자/공백 자동 처리)
    if st.button("로그인", type="primary", use_container_width=True):
        clean_id = input_id.strip().upper()
        clean_pw = input_pw.strip()
        login_check(clean_id, clean_pw)
    st.stop()

# ------------------------------------------------------------------
# 2. 데이터 로드 함수 (구글 시트 연결)
# ------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_google_sheet_data():
    try:
        # secrets에 저장된 서비스 계정 정보 사용
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # 운영독스 - 재고 시트 열기
        spreadsheet = client.open('에이젯광주 운영독스') 
        sheet = spreadsheet.worksheet('raw_운영부재고')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # --- [이름표 자동 정리] ---
        rename_map = {
            'B/L NO': 'BL넘버',         
            '식별번호': 'BL넘버',       
            'B/L NO,식별번호': 'BL넘버',
            'BL식별번호': 'BL넘버',
            'BL NO': 'BL넘버',
            '브랜드-등급-est': '브랜드' 
        }
        df.rename(columns=rename_map, inplace=True)
        # ------------------------
            
        # 품명 없는 행 삭제
        if '품명' in df.columns:
            df = df[df['품명'].astype(str).str.strip() != '']

        # 모든 텍스트 앞뒤 공백 제거
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        return df
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 3. 사이드바 (정보 및 새로고침)
# ------------------------------------------------------------------
with st.sidebar:
    # 접속자 정보 표시
    current_user = st.session_state.get('user_id', 'AZ')
    st.write(f"접속자: **{current_user}**")
    
    # 권한 표시
    if current_user == "AZS":
        st.success("✅ 출고 등록 권한 보유")
    else:
        st.info("ℹ️ 재고 조회 전용 모드")
        
    if st.button("로그아웃"):
        st.session_state['logged_in'] = False
        st.rerun()
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

# ------------------------------------------------------------------
# 4. 메인 화면: 재고 조회 및 필터링
# ------------------------------------------------------------------
st.title("🥩 에이젯광주 실시간 재고")
st.caption(f"기준 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

df = load_google_sheet_data()

if not df.empty:
    col1, col2 = st.columns(2)
    with col1:
        search_item = st.text_input("🔍 품명 검색")
    with col2:
        search_brand = st.text_input("🏢 브랜드 검색")
    
    filtered_df = df.copy()
    
    # 1단계: 검색 필터링
    if search_item:
        filtered_df = filtered_df[filtered_df['품명'].astype(str).str.contains(search_item, na=False)]
    
    if search_brand and '브랜드' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['브랜드'].astype(str).str.lower().str.startswith(search_brand.lower(), na=False)]

    # 2단계: 정렬 (본점 우선 -> 창고명 -> 품명)
    if '창고명' in filtered_df.columns:
        filtered_df['sort_order'] = filtered_df['창고명'].apply(lambda x: 0 if '본점' in str(x) else 1)
        filtered_df = filtered_df.sort_values(by=['sort_order', '창고명', '품명'], ascending=[True, True, True])
        filtered_df = filtered_df.drop(columns=['sort_order'])

    st.divider()
    
    # 3단계: 사용자별 컬럼 노출 설정
    current_user = st.session_state.get('user_id')
    
    if current_user == "AZ":
        # 관리자용: 기본 정보 중심
        target_cols = ['품명', '브랜드', '재고수량', '창고명', '소비기한', '평균중량']
        st.subheader(f"📊 재고 현황 (관리자): {len(filtered_df)}건")
        
    elif current_user == "AZS":
        # 영업용: BL넘버 포함 상세 정보
        target_cols = ['품명', '브랜드', '재고수량', 'BL넘버', '창고명', '소비기한', '평균중량']
        st.subheader(f"📑 상세 재고 조회: {len(filtered_df)}건")
        
    else:
        target_cols = []

    # 실제 시트에 존재하는 컬럼만 표시 (에러 방지)
    visible_cols = [col for col in target_cols if col in filtered_df.columns]

    if visible_cols:
        st.dataframe(filtered_df[visible_cols], use_container_width=True, hide_index=True)
    else:
        st.warning(f"표시할 데이터 컬럼을 찾을 수 없습니다. 시트 헤더를 확인해주세요.\n요청 컬럼: {target_cols}")

    # ------------------------------------------------------------------
    # 5. [추가 기능] 출고증 작성 기능 (AZS 계정 전용)
    # ------------------------------------------------------------------
    if current_user == "AZS":
        st.divider()
        st.header("🚚 출고 등록 (출고증 작성)")

        st.markdown("##### 1. 품목 선택")
        # 드롭다운 필터링을 위한 검색창
        release_search = st.text_input("🔍 품목 검색 (빈칸이면 전체 목록)", placeholder="예: 살치, KILCOY, 640 등")

        # 검색어에 따라 드롭다운 목록 필터링
        if release_search:
            condition = filtered_df['품명'].astype(str).str.contains(release_search, na=False) | \
                        filtered_df['브랜드'].astype(str).str.contains(release_search, na=False)
            target_df = filtered_df[condition]
        else:
            target_df = filtered_df

        if not target_df.empty:
            # BL넘버 예외처리
            if 'BL넘버' not in target_df.columns:
                target_df = target_df.copy()
                target_df['BL넘버'] = '-'
                
            # 선택지 텍스트 생성
            select_options = target_df.apply(
                lambda x: f"[{x['브랜드']}] {x['품명']} (재고: {x['재고수량']}) | BL: {x['BL넘버']}", axis=1
            )
            
            # 품목 선택 박스
            selected_index = st.selectbox("출고할 품목을 선택하세요:", select_options.index, format_func=lambda i: select_options[i])
            selected_row = target_df.loc[selected_index] # 원본 데이터에서 행 가져오기

            # 2. 입력 폼
            st.markdown("##### 2. 세부 정보 입력")
            with st.form("release_form"):
                f_col1, f_col2, f_col3 = st.columns(3)
                
                with f_col1:
                    input_date = st.date_input("출고일 (달력 선택)", datetime.now())
                    input_manager = st.text_input("담당자 (D열)", value="강경현")
                    input_client = st.text_input("거래처 (E열)")
                    
                with f_col2:
                    st.text_input("품명 (F열)", value=selected_row['품명'], disabled=True)
                    st.text_input("브랜드 (G열)", value=selected_row['브랜드'], disabled=True)
                    st.text_input("BL식별번호 (H열)", value=selected_row.get('BL넘버', '-'), disabled=True)
                    
                with f_col3:
                    input_qty = st.number_input("출고 수량 (I열)", min_value=1, value=1)
                    input_warehouse = st.text_input("창고 (J열)", value=selected_row.get('창고명', 'SWC'))
                    input_price = st.number_input("단가 (K열)", min_value=0, step=100)
                    input_transfer = st.checkbox("이체 여부 (L열)", value=True)

                submit_btn = st.form_submit_button("출고 등록하기", type="primary")

                if submit_btn:
                    try:
                        # 3. 출고증 파일 연결
                        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
                        creds_dict = st.secrets["gcp_service_account"]
                        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                        client_gs = gspread.authorize(creds)
                        
                        doc = client_gs.open('에이젯광주 출고증') 
                        sheet_out = doc.worksheet('출고증')
                        
                        # 4. 날짜 포맷 변환 ("1. 19" 형식)
                        target_date_str = f"{input_date.month}. {input_date.day}"
                        
                        # 5. 빈 행 찾기 (역순 탐색)
                        all_vals = sheet_out.get_all_values()
                        target_row_idx = -1
                        
                        for i in range(len(all_vals), 0, -1):
                            row = all_vals[i-1]
                            if len(row) > 2 and str(row[2]).strip() == target_date_str:
                                if len(row) <= 3 or str(row[3]).strip() == "":
                                    target_row_idx = i
                                    break
                        
                        if target_row_idx != -1:
                            # 6. 데이터 입력
                            transfer_text = "이체" if input_transfer else ""
                            
                            update_data = [
                                input_manager,                  
                                input_client,                   
                                selected_row['품명'],            
                                selected_row['브랜드'],          
                                selected_row.get('BL넘버', '-'), 
                                int(input_qty),                 
                                input_warehouse,                
                                int(input_price),               
                                transfer_text                   
                            ]
                            
                            rng = f"D{target_row_idx}:L{target_row_idx}"
                            sheet_out.update(rng, [update_data])
                            st.success(f"✅ {target_date_str} / {target_row_idx}행에 등록되었습니다!")
                            
                        else:
                            st.error(f"❌ '{target_date_str}' 날짜의 빈 칸(D열 공백)을 찾을 수 없습니다.")
                            st.info("💡 팁: 운영부에 해당 날짜의 빈 행을 추가해달라고 요청하세요.")
                            
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
        else:
            st.warning("검색 조건에 맞는 재고가 없습니다.")

else:
    st.info("데이터를 불러오는 중이거나 연결에 실패했습니다.")
