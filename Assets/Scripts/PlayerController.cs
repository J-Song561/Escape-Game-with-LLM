using UnityEngine;

public class PlayerController : MonoBehaviour
{
    public float speed = 5f;
    public float mouseSensitivity = 5f;

    public Transform playerCamera;

    public float jumpHeight = 1f;
    public float gravity = -9.81f;

    float xRotation = 0f;
    float yVelocity = 0f;

    CharacterController controller;

    public bool canControl = true;

    void Start()
    {
        controller = GetComponent<CharacterController>();
    }

    void Update()
    {
        if (!canControl) return;

        // 마우스 회전
        float mouseX = Input.GetAxis("Mouse X") * mouseSensitivity;
        float mouseY = Input.GetAxis("Mouse Y") * mouseSensitivity;

        xRotation -= mouseY;
        xRotation = Mathf.Clamp(xRotation, -90f, 90f);

        playerCamera.localRotation = Quaternion.Euler(xRotation, 0f, 0f);
        transform.Rotate(Vector3.up * mouseX);

        // 이동 (wasd)
        float x = Input.GetAxis("Horizontal");
        float z = Input.GetAxis("Vertical");

        Vector3 move = (transform.right * x + transform.forward * z) * speed;

        // 점프 (space)
        if (controller.isGrounded)
        {
            if (yVelocity < 0)
                yVelocity = -2f;

            if (Input.GetKeyDown(KeyCode.Space))
                yVelocity = Mathf.Sqrt(jumpHeight * -2f * gravity);
        }

        // 중력 계산
        yVelocity += gravity * Time.deltaTime;

        Vector3 velocity = move;
        velocity.y = yVelocity;

        controller.Move(velocity * Time.deltaTime);
    }
}