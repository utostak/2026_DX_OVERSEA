' ============================================================
' [사용법] 이 코드 전체를 해당 시트 모듈(Sheet VBA)에 붙여넣기만 하면 됩니다.
'
'   - Ctrl + 더블클릭 시 URL을 즉시 계산하여 기본 브라우저로 팝업합니다.
'   - 별도 매크로 실행 불필요. 사전 작업 없음.
'
'   URL 규칙: https://liw.lge.com/active-orders?le=LGEPH&cur=PHP&pg={PG}&biz={BIZ}
'     · {PG}  = 헤더 행(4행)의 해당 컬럼 값
'     · {BIZ} = BIZ 컬럼(3열)의 해당 행 값
'   대상 영역: GV~HD (204~212열), HH~PH (216~224열) / 50~98행
' ============================================================

Private Declare PtrSafe Function GetAsyncKeyState Lib "user32" (ByVal vKey As Integer) As Integer

Private Sub Worksheet_BeforeDoubleClick(ByVal Target As Range, Cancel As Boolean)

    Const VK_CONTROL      As Integer = &H11
    Const BASE_URL        As String  = "https://liw.lge.com/active-orders"
    Const LE_PARAM        As String  = "LGEPH"
    Const CUR_PARAM       As String  = "PHP"
    Const HEADER_ROW      As Long    = 4
    Const BIZ_COL         As Long    = 3
    Const DATA_START_ROW  As Long    = 50
    Const DATA_END_ROW    As Long    = 98

    ' Ctrl 키가 눌려 있지 않으면 무시
    If (GetAsyncKeyState(VK_CONTROL) And &H8000) = 0 Then Exit Sub

    Dim r As Long, c As Long
    r = Target.Row
    c = Target.Column

    ' 대상 행/열 범위 확인 (GV~HD: 204~212, HH~PH: 216~224 / 50~98행)
    Dim inRange As Boolean
    inRange = (r >= DATA_START_ROW And r <= DATA_END_ROW) And _
              ((c >= 204 And c <= 212) Or (c >= 216 And c <= 224))

    If Not inRange Then Exit Sub

    ' 숫자 값이 있는 셀만 처리
    Dim cellVal As Variant
    cellVal = Target.Value
    If Not (IsNumeric(cellVal) And cellVal > 0) Then Exit Sub

    ' URL 계산
    Dim pgVal  As String
    Dim bizVal As String
    pgVal  = Trim(CStr(Me.Cells(HEADER_ROW, c).Value))
    bizVal = UCase(Trim(CStr(Me.Cells(r, BIZ_COL).Value)))

    If pgVal = "" Or bizVal = "" Then Exit Sub

    Dim url As String
    url = BASE_URL & "?" & _
          "le=" & LE_PARAM & _
          "&cur=" & CUR_PARAM & _
          "&pg=" & pgVal & _
          "&biz=" & bizVal

    ' 더블클릭 편집 진입 방지
    Cancel = True

    ' 기본 브라우저로 URL 열기
    Shell "cmd /c start """" """ & url & """", vbHide

End Sub

