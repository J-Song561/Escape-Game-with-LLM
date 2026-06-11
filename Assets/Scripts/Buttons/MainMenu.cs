using UnityEngine;
using UnityEngine.SceneManagement;

public class MainMenu : MonoBehaviour
{
    // Start Game
    public void StartGame()
    {
        SceneManager.LoadScene("GameScreen");
    }

    // Quit Game
    public void QuitGame()
    {
        Debug.Log("Game Closed");

        Application.Quit();
    }
}