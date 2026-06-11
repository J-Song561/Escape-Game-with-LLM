using UnityEngine;

public class DayNightCycle : MonoBehaviour
{
    [Header("Light")]
    public Light sun;

    [Header("Time Settings")]
    public float dayDurationInSeconds = 120f;
    public float timeOfDay = 0.25f;

    [Header("Light Intensity")]
    public float maxSunIntensity = 1.2f;
    public float minSunIntensity = 0.05f;

    [Header("Sky Colors")]
    public Color dayAmbientColor = new Color(0.75f, 0.75f, 0.75f);
    public Color nightAmbientColor = new Color(0.05f, 0.05f, 0.08f);

    private void Update()
    {
        timeOfDay += Time.deltaTime / dayDurationInSeconds;

        if (timeOfDay >= 1f)
        {
            timeOfDay = 0f;
        }

        UpdateLighting();
    }

    private void UpdateLighting()
    {
        float sunRotation = timeOfDay * 360f - 90f;
        sun.transform.rotation = Quaternion.Euler(sunRotation, 170f, 0f);

        float intensity = Mathf.Clamp01(Mathf.Sin(timeOfDay * Mathf.PI));

        sun.intensity = Mathf.Lerp(minSunIntensity, maxSunIntensity, intensity);

        RenderSettings.ambientLight = Color.Lerp(
            nightAmbientColor,
            dayAmbientColor,
            intensity
        );
    }
}