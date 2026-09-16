using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;

/// <summary>
/// 게임 전체에서 단 하나만 존재하는 세션 관리자.
///
/// 플레이어가 게임을 시작하면(= 이 컴포넌트가 처음 참조되는 순간)
/// SessionId가 자동으로 생성되고, 씬이 바뀌어도 사라지지 않는다.
/// ChatManager 등 대화를 서버로 보내는 모든 곳에서
/// GameSession.Instance.SessionId 를 사용하면
/// NPC 4명이 전부 같은 세션 안에서 대화가 저장된다.
///
/// 씬에 미리 배치할 필요 없음 — 처음 Instance를 부르는 순간
/// 자동으로 GameObject가 생성된다.
///
/// [전시장용 엔딩수집함]
/// 한 방문자가 플레이 중 여러 번 재시도(RestartPlaythrough)해서
/// 서로 다른 엔딩을 보는 경우, 그 방문자가 지금까지 본 엔딩은
/// 전부 같은 세션(SessionId) 안에 쌓인다.
/// 완전히 새로운 방문자로 넘어갈 때는 StartNewVisit()을 호출해서
/// 세션ID와 엔딩수집함을 둘 다 초기화한다.
/// 엔딩 기록은 서버에도 같이 저장되므로, 관리자는 /admin/endings 로
/// 전시장에서 나온 모든 방문자의 엔딩 기록을 한 번에 조회할 수 있다.
/// </summary>
public class GameSession : MonoBehaviour
{
    private static GameSession _instance;

    public static GameSession Instance
    {
        get
        {
            if (_instance == null)
            {
                // 씬에 이미 존재하면 그걸 사용
                _instance = FindObjectOfType<GameSession>();

                // 없으면 자동 생성 (게임 플레이 시작 시점에 최초 생성됨)
                if (_instance == null)
                {
                    var go = new GameObject("GameSession");
                    _instance = go.AddComponent<GameSession>();
                }
            }
            return _instance;
        }
    }

    /// <summary>현재 플레이스루의 세션 ID. 게임이 시작되면 자동으로 채워진다.</summary>
    public string SessionId { get; private set; }

    [Header("엔딩 수집함 서버 기록 (선택사항)")]
    [Tooltip("비워두면 서버에는 기록하지 않고 로컬(이번 세션 동안)에만 쌓인다.")]
    public string endingsApiUrl = "https://여기에ngrok주소/endings/unlock";

    /// <summary>
    /// 이번 방문(세션) 동안 이 방문자가 해금한 엔딩 id 목록.
    /// RestartPlaythrough()로 재시도해도 유지되고, StartNewVisit()을 부르면 초기화된다.
    /// </summary>
    public List<string> UnlockedEndingsThisSession { get; private set; } = new List<string>();

    private void Awake()
    {
        // 씬 재로드 등으로 중복 생성되는 경우 기존 인스턴스를 유지
        if (_instance != null && _instance != this)
        {
            Destroy(gameObject);
            return;
        }

        _instance = this;
        DontDestroyOnLoad(gameObject);

        // 게임 플레이 시작 시 세션 ID 자동 생성
        GenerateNewSessionId();
    }

    /// <summary>
    /// 타이틀 화면에서 '새 게임'을 눌렀을 때처럼
    /// 완전히 새로운 플레이스루를 시작하고 싶을 때 호출한다.
    /// 이전 세션의 대화 기록/요약은 서버(DB)에 그대로 남고,
    /// 새로 발급된 SessionId로 새 대화가 시작된다.
    /// </summary>
    public void GenerateNewSessionId()
    {
        SessionId = System.Guid.NewGuid().ToString();
        Debug.Log($"[GameSession] 세션 시작: {SessionId}");
    }

    // ── 엔딩 수집함 ──────────────────────────────

    /// <summary>
    /// 엔딩 씬에 도달했을 때 호출한다.
    /// 이번 세션의 로컬 목록에 추가하고(중복 방지), 관리자가 전체 조회할 수 있도록
    /// 서버에도 같은 기록을 남긴다.
    /// </summary>
    public void UnlockEnding(string endingId)
    {
        if (string.IsNullOrEmpty(endingId)) return;

        if (!UnlockedEndingsThisSession.Contains(endingId))
        {
            UnlockedEndingsThisSession.Add(endingId);
            Debug.Log($"[GameSession] 엔딩 해금: {endingId} (세션: {SessionId})");
        }

        if (!string.IsNullOrEmpty(endingsApiUrl))
            StartCoroutine(SendEndingToServer(endingId));
    }

    private IEnumerator SendEndingToServer(string endingId)
    {
        var body = new EndingUnlockRequest { session_id = SessionId, ending_id = endingId };
        string json = JsonUtility.ToJson(body);

        using (var req = new UnityWebRequest(endingsApiUrl, "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            req.SetRequestHeader("ngrok-skip-browser-warning", "true");

            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogWarning(
                    $"[GameSession] 엔딩 서버 기록 실패({endingId}) → {req.responseCode} {req.error}");
            }
        }
    }

    /// <summary>
    /// 같은 방문자가 "다른 엔딩 보러 다시 플레이"할 때 호출한다.
    /// 세션ID는 그대로 유지되므로 엔딩수집함도 계속 누적된다.
    /// 엔딩 화면의 "다시 플레이" 버튼에 연결하면 된다.
    /// </summary>
    public void RestartPlaythrough(string gameplaySceneName)
    {
        SceneManager.LoadScene(gameplaySceneName);
    }

    /// <summary>
    /// 완전히 새로운 방문자가 시작할 때 호출한다.
    /// (예: 대기/타이틀 화면의 "체험 시작" 버튼)
    /// 새 세션ID를 발급하고, 이전 방문자의 엔딩수집함을 초기화한다.
    /// 서버에 남은 이전 방문자의 기록은 그대로 유지된다 — 관리자는 언제든 조회 가능.
    /// </summary>
    public void StartNewVisit()
    {
        GenerateNewSessionId();
        UnlockedEndingsThisSession.Clear();
    }
}

/// <summary>ChatManager의 Message/ChatRequest와 같은 방식의 JsonUtility용 DTO.</summary>
[System.Serializable]
public class EndingUnlockRequest
{
    public string session_id;
    public string ending_id;
}
