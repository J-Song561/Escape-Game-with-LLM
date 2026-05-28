using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class ClueDetailUI : MonoBehaviour
{
    public static ClueDetailUI instance;

    public GameObject panel;

    public Image clueImage;
    public TMP_Text clueName;
    public TMP_Text clueDescription;

    private List<ClueData> clueList;
    private int currentIndex;

    private void Awake()
    {
        instance = this;
    }

    public void ShowClue(ClueData clue)
    {
        clueList = InventoryManager.instance.items;

        currentIndex = clueList.IndexOf(clue);

        panel.SetActive(true);

        UpdateUI();
    }

    void UpdateUI()
    {
        ClueData clue = clueList[currentIndex];

        clueImage.sprite = clue.icon;
        clueName.text = clue.clueName;
        clueDescription.text = clue.description;
    }

    public void NextClue()
    {
        currentIndex++;

        if (currentIndex >= clueList.Count)
            currentIndex = 0;

        UpdateUI();
    }

    public void PreviousClue()
    {
        currentIndex--;

        if (currentIndex < 0)
            currentIndex = clueList.Count - 1;

        UpdateUI();
    }

    public void ClosePanel()
    {
        panel.SetActive(false);
    }
}