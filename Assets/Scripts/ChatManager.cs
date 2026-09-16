using System.Collections;
using System.Collections.Generic;
using System.Text;
using TMPro;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;

public class ChatManager : MonoBehaviour
{
    [Header("API 설정")]
    public string apiUrl = "https://여기에ngrok주소/chat";

    [Header("NPC 설정")]
    public string npcId = "ella";                       // ella / louis / hailey / maria
    public string npcDisplayName = "엘라 부인";          // 채팅창에 표시될 이름

    [Header("UI 연결")]
    public TMP_InputField inputField;
    public Button sendButton;
    public TextMeshProUGUI chatLog;
    public ScrollRect scrollRect;

    [Header("옵션")]
    public int timeoutSeconds = 60;                     // LLM이 느리므로 넉넉하게

    // ─────────────────────────────────────────────
    // 세션 ID — NPC 4명이 반드시 같은 값을 써야 한다.
    // static이라 ChatManager가 몇 개든 하나만 생성된다.
    // 나중에 GameSession.cs를 만들면 아래 SessionId를
    // GameSession.Instance.SessionId 로 교체하면 된다.
    // ─────────────────────────────────────────────
    private static string _sessionId;
    private static string SessionId
    {
        get
        {
            if (string.IsNullOrEmpty(_sessionId))
            {
                _sessionId = System.Guid.NewGuid().ToString();
                Debug.Log($"[ChatManager] 세션 시작: {_sessionId}");
            }
            return _sessionId;
        }
    }

    private readonly List<string> lines = new List<string>();
    private bool isWaiting = false;

    void Start()
    {
        sendButton.onClick.AddListener(OnSendClicked);
        inputField.onSubmit.AddListener(_ => OnSendClicked());   // 엔터키 전송
    }

    void OnEnable()
    {
        // 응답 대기 중에 대화창을 닫으면 코루틴이 강제 중단되어
        // isWaiting = true, 입력창 비활성 상태가 그대로 남는다.
        // 다시 열 때 초기화해서 입력이 잠기지 않게 한다.
        isWaiting = false;
        SetInputEnabled(true);

        // 입력창 비우고 포커스
        if (inputField != null)
        {
            inputField.text = "";
            inputField.ActivateInputField();
        }
    }

    public void OnSendClicked()
    {
        if (isWaiting) return;                    // 응답 대기 중 중복 전송 차단

        string userText = inputField.text.Trim();
        if (string.IsNullOrEmpty(userText)) return;

        AppendLine("나", userText);
        inputField.text = "";
        StartCoroutine(SendToAPI(userText));
    }

    IEnumerator SendToAPI(string userText)
    {
        isWaiting = true;
        SetInputEnabled(false);
        AppendLine(npcDisplayName, "…");          // 타이핑 인디케이터

        var requestData = new ChatRequest
        {
            npc = npcId,
            session_id = SessionId,
            messages = new Message[]
            {
                // 최신 발화 1개만 보낸다. 이전 대화는 서버가 자체 관리.
                new Message { role = "user", content = userText }
            }
        };
        string jsonBody = JsonUtility.ToJson(requestData);

        using (var req = new UnityWebRequest(apiUrl, "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(jsonBody));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            req.SetRequestHeader("ngrok-skip-browser-warning", "true");  // ngrok 경고페이지 우회
            req.timeout = timeoutSeconds;

            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                ChatResponse res = null;
                try
                {
                    res = JsonUtility.FromJson<ChatResponse>(req.downloadHandler.text);
                }
                catch (System.Exception e)
                {
                    Debug.LogError($"[ChatManager:{npcId}] 파싱 실패 → {e.Message}\n응답 원문: {req.downloadHandler.text}");
                }

                if (res != null && !string.IsNullOrEmpty(res.reply))
                    ReplaceLastLine(npcDisplayName, res.reply);       // "…" → 실제 응답
                else
                    ReplaceLastLine("시스템", $"응답 파싱 실패 (원문: {req.downloadHandler.text})");
            }
            else
            {
                Debug.LogError($"[ChatManager:{npcId}] 요청 실패 → {req.responseCode} / {req.error}");
                ReplaceLastLine("시스템", $"연결 오류: {req.responseCode} {req.error}");
            }
        }

        SetInputEnabled(true);
        isWaiting = false;
        inputField.ActivateInputField();
    }

    // ── UI 헬퍼 ──────────────────────────────

    void AppendLine(string speaker, string text)
    {
        lines.Add($"<b>{speaker}</b>: {text}");
        Render();
    }

    void ReplaceLastLine(string speaker, string text)
    {
        string formatted = $"<b>{speaker}</b>: {text}";
        if (lines.Count > 0) lines[lines.Count - 1] = formatted;
        else lines.Add(formatted);
        Render();
    }

    void Render()
    {
        if (chatLog != null)
            chatLog.text = string.Join("\n\n", lines);

        // 비활성 상태에서 StartCoroutine을 부르면 유니티가 에러를 낸다
        if (isActiveAndEnabled)
            StartCoroutine(ScrollToBottomNextFrame());
    }

    IEnumerator ScrollToBottomNextFrame()
    {
        yield return null;                        // 레이아웃 갱신 후 스크롤해야 정확함
        Canvas.ForceUpdateCanvases();
        if (scrollRect != null)
            scrollRect.verticalNormalizedPosition = 0f;
    }

    void SetInputEnabled(bool value)
    {
        if (inputField != null) inputField.interactable = value;
        if (sendButton != null) sendButton.interactable = value;
    }

    /// <summary>화면의 대화 로그만 지운다. 서버의 대화 기억은 유지된다.</summary>
    public void ClearHistory()
    {
        lines.Clear();
        if (chatLog != null) chatLog.text = "";
    }
}