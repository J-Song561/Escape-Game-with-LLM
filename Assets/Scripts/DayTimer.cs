using UnityEngine;

public class DayTimer : MonoBehaviour
{
    public Light sun;

    public float dayLengthSeconds = 180f;

    public float maxSunIntensity = 1.2f;
    public float minSunIntensity = 0.02f;

    public Color dayAmbientColor = new Color(0.75f, 0.75f, 0.75f);
    public Color nightAmbientColor = new Color(0.03f, 0.03f, 0.06f);

    private float timer;
    public bool IsNight { get; private set; }

    private void Update()
    {
        if (IsNight) return;

        timer += Time.deltaTime;

        float progress = Mathf.Clamp01(timer / dayLengthSeconds);

        UpdateLighting(progress);

        if (progress >= 1f)
        {
            IsNight = true;
            Debug.Log("Night has started. Player should go to bed.");
        }
    }

    private void UpdateLighting(float progress)
    {
        float sunAngle = Mathf.Lerp(30f, 190f, progress);
        sun.transform.rotation = Quaternion.Euler(sunAngle, 170f, 0f);

        sun.intensity = Mathf.Lerp(maxSunIntensity, minSunIntensity, progress);

        RenderSettings.ambientLight = Color.Lerp(
            dayAmbientColor,
            nightAmbientColor,
            progress
        );
    }
}