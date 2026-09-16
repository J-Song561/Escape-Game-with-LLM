using UnityEngine;
using TMPro;

public class CurrentDayUI : MonoBehaviour
{
    public TMP_Text dayText;

    private void Start()
    {
        UpdateDayText();
    }

    private void UpdateDayText()
    {
        dayText.text = "Day " + GameProgress.CurrentDay;
    }
}