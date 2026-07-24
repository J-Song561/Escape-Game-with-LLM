using UnityEngine;

public class NPC : MonoBehaviour
{
    public Transform player;
    public GameObject talkUI;
    public GameObject hintUI;

    public PlayerController playerController;

    public float distance = 2f;

    void Update()
    {
        float d = Vector3.Distance(player.position, transform.position);

        bool canTalk = d < distance;

        hintUI.SetActive(canTalk);

        if (canTalk && Input.GetKeyDown(KeyCode.E))
        {
            bool isOpening = !talkUI.activeSelf;
            talkUI.SetActive(isOpening);

            if (playerController != null)
                playerController.canControl = !isOpening;
        }
    }
}