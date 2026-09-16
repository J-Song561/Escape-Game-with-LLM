using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using TMPro;

public class DaySelectMenu : MonoBehaviour
{
    public Button[] dayButtons;
    public TMP_Text[] dayTexts;

    public Color normalColor = Color.white;
    public Color activeColor = Color.yellow;

    private void Start()
    {
        UpdateDaysUI();
    }

    private void UpdateDaysUI()
    {
        for (int i = 0; i < dayButtons.Length; i++)
        {
            int dayNumber = i + 1;

            bool isCurrentDay = dayNumber == GameProgress.CurrentDay;

            dayButtons[i].interactable = isCurrentDay;

            dayTexts[i].color = isCurrentDay ? activeColor : normalColor;
            dayTexts[i].fontStyle = isCurrentDay ? FontStyles.Bold : FontStyles.Normal;
        }
    }

    public void StartCurrentDay()
    {
        SceneManager.LoadScene("GameScreen");
    }
}