using UnityEngine;

public class PlayerSpawnManager : MonoBehaviour
{
    public Transform player;
    public Transform bedSpawnPoint;

    private void Start()
    {
        SpawnPlayerNearBed();
    }

    private void SpawnPlayerNearBed()
    {
        CharacterController characterController = player.GetComponent<CharacterController>();

        if (characterController != null)
        {
            characterController.enabled = false;
        }

        player.position = bedSpawnPoint.position;
        player.rotation = bedSpawnPoint.rotation;

        if (characterController != null)
        {
            characterController.enabled = true;
        }
    }
}