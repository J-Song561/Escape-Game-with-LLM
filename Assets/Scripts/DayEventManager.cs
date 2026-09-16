using UnityEngine;

public class DayEventManager : MonoBehaviour
{
    public GameObject[] dayEvents;
    private void Start()
    {
        ActivateCurrentDayEvents();
    }

    private void ActivateCurrentDayEvents()
    {
        for (int i = 0; i < dayEvents.Length; i++)
        {
            if (dayEvents[i] != null)
            {
                dayEvents[i].SetActive(false);
            }
        }

        int index = GameProgress.CurrentDay - 1;

        if (index >= 0 && index < dayEvents.Length)
        {
            dayEvents[index].SetActive(true);
        }
    }
}