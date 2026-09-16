using UnityEngine;
using UnityEngine.SceneManagement;

public class MainMenu : MonoBehaviour
{
    // Start Game
    public void StartGame()
    {
        GameProgress.CurrentDay = 1;
        SceneManager.LoadScene("DaySelectScreen");
    }

    // Quit Game
    public void QuitGame()
    {
        Debug.Log("Game Closed");

        Application.Quit();
    }
}