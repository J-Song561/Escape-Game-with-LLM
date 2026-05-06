using UnityEngine;

public class UIManager : MonoBehaviour
{
    public GameObject inventoryPanel; // 가방
    public GameObject notePanel;      // 노트

    public PlayerController player;

    void Start()
    {
        inventoryPanel.SetActive(false);
        notePanel.SetActive(false);

        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;

        player.canControl = true;
    }

    // 가방
    public void ToggleInventory()
    {
        bool open = !inventoryPanel.activeSelf;

        inventoryPanel.SetActive(open);
        notePanel.SetActive(false); 

        player.canControl = !open;

        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;
    }

    // 노트
    public void ToggleNote()
    {
        bool open = !notePanel.activeSelf;

        notePanel.SetActive(open);
        inventoryPanel.SetActive(false); 

        player.canControl = !open;

        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;
    }
}