using UnityEngine;

[CreateAssetMenu(fileName = "New Clue", menuName = "Clue")]
public class ClueData : ScriptableObject
{
    public string clueName;
    public Sprite icon;
    public string description;
}