using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;
using System.Collections;
using System.Collections.Generic;
using TMPro;

public class ChatManager : MonoBehaviour
{
    [Header("API 설정")]
    public string apiUrl = "https://여기에ngrok주소/chat";
    public string npcId = "ella";

    [Header("UI 연결")]
    public TMP_InputField inputField;
    public Button sendButton;
    public TextMeshProUGUI chatLog;
    public ScrollRect scrollRect;

    private List<Message> messageHistory = new List<Message>();

    void Start()
    {
        sendButton.onClick.AddListener(OnSendClicked);
    }

    void OnEnable()
    {
        // 채팅창 열릴 때마다 입력창 포커스
        if (inputField != null)
            inputField.Select();
    }

    public void OnSendClicked()
    {
        string userText = inputField.text.Trim();
        if (string.IsNullOrEmpty(userText)) return;

        AppendChat("나", userText);
        inputField.text = "";

        messageHistory.Add(new Message { role = "user", content = userText });
        StartCoroutine(SendToAPI());
    }

    IEnumerator SendToAPI()
    {
        sendButton.interactable = false;
        AppendChat(npcId, "...");  // 로딩 표시

        var requestData = new ChatRequest
        {
            npc = npcId,
            messages = messageHistory.ToArray()
        };

        string jsonBody = JsonUtility.ToJson(requestData);

        using var req = new UnityWebRequest(apiUrl, "POST");
        req.uploadHandler = new UploadHandlerRaw(
            System.Text.Encoding.UTF8.GetBytes(jsonBody));
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");

        yield return req.SendWebRequest();

        // "..." 제거
        chatLog.text = chatLog.text.Substring(
            0, chatLog.text.LastIndexOf($"\n<b>{npcId}</b>: ..."));

        if (req.result == UnityWebRequest.Result.Success)
        {
            var res = JsonUtility.FromJson<ChatResponse>(req.downloadHandler.text);
            AppendChat(npcId, res.reply);
            messageHistory.Add(new Message { role = "assistant", content = res.reply });
        }
        else
        {
            AppendChat("시스템", "연결 오류: " + req.error);
        }

        sendButton.interactable = true;
        Canvas.ForceUpdateCanvases();
        scrollRect.verticalNormalizedPosition = 0f;
    }

    void AppendChat(string speaker, string text)
    {
        chatLog.text += $"\n<b>{speaker}</b>: {text}";
    }

    public void ClearHistory()
    {
        messageHistory.Clear();
        chatLog.text = "";
    }
}