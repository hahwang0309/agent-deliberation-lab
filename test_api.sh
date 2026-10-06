#!/bin/bash

echo "==================================="
echo "행정조사 중복 판별 API 테스트 스크립트"
echo "==================================="
echo ""

API_BASE="http://localhost:8000"

# 1. 헬스 체크
echo "1️⃣  헬스 체크..."
curl -s "${API_BASE}/health" | python -m json.tool
echo ""
echo ""

# 2. 분석 요청
echo "2️⃣  분석 요청 중..."
RESPONSE=$(curl -s -X POST "${API_BASE}/api/v1/investigations" \
  -H "Content-Type: application/json" \
  -d @test_investigation_request.json)

echo "$RESPONSE" | python -m json.tool

# analysis_id 추출
ANALYSIS_ID=$(echo "$RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('analysis_id', ''))")

if [ -z "$ANALYSIS_ID" ]; then
    echo "❌ 분석 요청 실패!"
    exit 1
fi

echo ""
echo "✅ 분석 시작됨! ID: $ANALYSIS_ID"
echo ""

# 3. 상태 폴링
echo "3️⃣  분석 진행 상태 확인 중..."
MAX_ATTEMPTS=60  # 5분 (5초 * 60)
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    sleep 5
    ATTEMPT=$((ATTEMPT + 1))
    
    STATUS_RESPONSE=$(curl -s "${API_BASE}/api/v1/investigations/${ANALYSIS_ID}")
    STATUS=$(echo "$STATUS_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('status', ''))")
    
    echo "   [${ATTEMPT}/${MAX_ATTEMPTS}] 상태: $STATUS"
    
    if [ "$STATUS" = "completed" ]; then
        echo ""
        echo "🎉 분석 완료!"
        echo ""
        echo "4️⃣  분석 결과:"
        echo "$STATUS_RESPONSE" | python -m json.tool
        echo ""
        
        # 5. 보고서 다운로드
        echo "5️⃣  보고서 다운로드..."
        curl -s "${API_BASE}/api/v1/investigations/${ANALYSIS_ID}/report" > "report_${ANALYSIS_ID}.md"
        echo "✅ 보고서 저장: report_${ANALYSIS_ID}.md"
        echo ""
        
        # 보고서 미리보기 (처음 30줄)
        echo "📄 보고서 미리보기:"
        echo "-----------------------------------"
        head -n 30 "report_${ANALYSIS_ID}.md"
        echo "-----------------------------------"
        echo ""
        echo "✨ 테스트 완료!"
        exit 0
    elif [ "$STATUS" = "failed" ]; then
        echo ""
        echo "❌ 분석 실패!"
        echo "$STATUS_RESPONSE" | python -m json.tool
        exit 1
    fi
done

echo ""
echo "⏱️  타임아웃: 5분 이상 소요되고 있습니다."
echo "   다음 명령으로 직접 확인하세요:"
echo "   curl ${API_BASE}/api/v1/investigations/${ANALYSIS_ID}"

