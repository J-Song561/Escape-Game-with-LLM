using UnityEngine;
using UnityEngine.SceneManagement;
using TMPro;

public class BedSleepTrigger : MonoBehaviour
{
    public DayTimer dayTimer;
    public GameObject sleepPromptText;

    private bool playerNearBed;

    private void Start()
    {
        sleepPromptText.SetActive(false);
    }

    private void Update()
    {
        if (playerNearBed && dayTimer != null && dayTimer.IsNight)
        {
            sleepPromptText.SetActive(true);

            if (Input.GetKeyDown(KeyCode.E))
            {
                GoToNextDay();
            }
        }
        else
        {
            sleepPromptText.SetActive(false);
        }
    }

    private void GoToNextDay()
    {
        if (GameProgress.CurrentDay >= 7)
        {
            SceneManager.LoadScene("MainScreen");
        }
        else
        {
            GameProgress.CurrentDay++;
            SceneManager.LoadScene("DaySelectScreen");
        }
    }

    private void OnTriggerEnter(Collider other)
    {
        if (other.CompareTag("Player"))
        {
            playerNearBed = true;
        }
    }

    private void OnTriggerExit(Collider other)
    {
        if (other.CompareTag("Player"))
        {
            playerNearBed = false;
        }
    }
}