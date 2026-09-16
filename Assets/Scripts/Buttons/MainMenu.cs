using UnityEngine;
using UnityEngine.SceneManagement;

public class MainMenu : MonoBehaviour
{
    [Tooltip("플레이 화면 씬 이름")]
    public string gameSceneName = "GameScreen";

    // Start Game
    // 완전히 새로운 방문자가 "시작"을 누른 것으로 간주하고
    // 새 세션ID를 발급 + 이전 방문자의 엔딩수집함을 초기화한 뒤 게임 씬으로 이동한다.
    public void StartGame()
    {
        GameSession.Instance.StartNewVisit();
        SceneManager.LoadScene(gameSceneName);
    }

    // Quit Game
    public void QuitGame()
    {
        Debug.Log("Game Closed");

        Application.Quit();
    }
}
