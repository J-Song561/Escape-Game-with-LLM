using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class InventorySlot : MonoBehaviour
{
    public Image icon;
    public TextMeshProUGUI itemName;

    private ClueData currentItem;

    public void SetItem(ClueData item)
    {
        currentItem = item;

        icon.sprite = item.icon;
        itemName.text = item.clueName;
    }

    public void OnClickSlot()
    {
        FindObjectOfType<ClueDetailUI>().ShowClue(currentItem);
    }
}