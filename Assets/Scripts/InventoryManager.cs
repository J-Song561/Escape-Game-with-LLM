using System.Collections.Generic;
using UnityEngine;

public class InventoryManager : MonoBehaviour
{
    public static InventoryManager instance;

    public Transform slotParent;
    public GameObject slotPrefab;

    public List<ClueData> items = new List<ClueData>();

    private void Awake()
    {
        instance = this;
    }

    public void AddItem(ClueData item)
    {
        items.Add(item);

        GameObject newSlot = Instantiate(slotPrefab, slotParent);

        newSlot.GetComponent<InventorySlot>().SetItem(item);
    }
}