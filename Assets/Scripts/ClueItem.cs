using UnityEngine;

public class ClueItem : MonoBehaviour
{
    public ClueData clueData;

    private void OnMouseDown()
    {
        Debug.Log("클릭됨!");

        InventoryManager.instance.AddItem(clueData);

        Destroy(gameObject);
    }
}