"""
API 테스트 스크립트
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_register():
    """회원가입 테스트"""
    print("\n=== 1. 회원가입 테스트 ===")
    
    url = f"{BASE_URL}/api/v1/auth/register"
    data = {
        "email": "test@example.com",
        "password": "TestPass123!",
        "name": "테스트 사용자",
        "organization": "테스트 회사"
    }
    
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    return response.status_code == 201


def test_login():
    """로그인 테스트"""
    print("\n=== 2. 로그인 테스트 ===")
    
    url = f"{BASE_URL}/api/v1/auth/login"
    data = {
        "email": "test@example.com",
        "password": "TestPass123!"
    }
    
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Response: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200:
        return result.get("access_token"), result.get("refresh_token")
    return None, None


def test_get_my_info(access_token):
    """내 정보 조회 테스트"""
    print("\n=== 3. 내 정보 조회 테스트 ===")
    
    url = f"{BASE_URL}/api/v1/users/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    return response.status_code == 200


def test_update_my_info(access_token):
    """내 정보 수정 테스트"""
    print("\n=== 4. 내 정보 수정 테스트 ===")
    
    url = f"{BASE_URL}/api/v1/users/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    data = {
        "name": "수정된 이름",
        "organization": "새로운 회사"
    }
    
    response = requests.put(url, json=data, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    return response.status_code == 200


def test_change_password(access_token):
    """비밀번호 변경 테스트"""
    print("\n=== 5. 비밀번호 변경 테스트 ===")
    
    url = f"{BASE_URL}/api/v1/users/me/password"
    headers = {"Authorization": f"Bearer {access_token}"}
    data = {
        "current_password": "TestPass123!",
        "new_password": "NewTestPass456!"
    }
    
    response = requests.put(url, json=data, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    return response.status_code == 200


def test_refresh_token(refresh_token):
    """토큰 갱신 테스트"""
    print("\n=== 6. 토큰 갱신 테스트 ===")
    
    url = f"{BASE_URL}/api/v1/auth/refresh"
    data = {"refresh_token": refresh_token}
    
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200:
        return response.json().get("access_token")
    return None


def main():
    """메인 테스트 실행"""
    print("="*60)
    print("API 테스트 시작")
    print("="*60)
    
    # 서버 상태 확인
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print("❌ 서버가 실행되고 있지 않습니다.")
            print("   먼저 'python api/main.py' 명령으로 서버를 실행하세요.")
            return
    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다.")
        print("   먼저 'python api/main.py' 명령으로 서버를 실행하세요.")
        return
    
    results = []
    
    # 1. 회원가입
    try:
        results.append(("회원가입", test_register()))
    except Exception as e:
        print(f"❌ 회원가입 실패: {e}")
        results.append(("회원가입", False))
    
    # 2. 로그인
    try:
        access_token, refresh_token = test_login()
        results.append(("로그인", access_token is not None))
        
        if not access_token:
            print("\n❌ 로그인 실패. 나머지 테스트를 건너뜁니다.")
            return
    except Exception as e:
        print(f"❌ 로그인 실패: {e}")
        results.append(("로그인", False))
        return
    
    # 3. 내 정보 조회
    try:
        results.append(("내 정보 조회", test_get_my_info(access_token)))
    except Exception as e:
        print(f"❌ 내 정보 조회 실패: {e}")
        results.append(("내 정보 조회", False))
    
    # 4. 내 정보 수정
    try:
        results.append(("내 정보 수정", test_update_my_info(access_token)))
    except Exception as e:
        print(f"❌ 내 정보 수정 실패: {e}")
        results.append(("내 정보 수정", False))
    
    # 5. 비밀번호 변경
    try:
        results.append(("비밀번호 변경", test_change_password(access_token)))
    except Exception as e:
        print(f"❌ 비밀번호 변경 실패: {e}")
        results.append(("비밀번호 변경", False))
    
    # 6. 토큰 갱신
    try:
        new_access_token = test_refresh_token(refresh_token)
        results.append(("토큰 갱신", new_access_token is not None))
    except Exception as e:
        print(f"❌ 토큰 갱신 실패: {e}")
        results.append(("토큰 갱신", False))
    
    # 결과 요약
    print("\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)
    
    for test_name, success in results:
        status = "✅ 통과" if success else "❌ 실패"
        print(f"{test_name}: {status}")
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    print(f"\n총 {total_count}개 테스트 중 {success_count}개 통과")
    
    if success_count == total_count:
        print("\n🎉 모든 테스트 통과!")
    else:
        print(f"\n⚠️  {total_count - success_count}개 테스트 실패")


if __name__ == "__main__":
    main()

