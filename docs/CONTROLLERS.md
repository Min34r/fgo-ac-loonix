# Fate/Grand Order Arcade - Controller & Input Configuration

This guide explains how arcade cabinet inputs are mapped to modern gamepads (PlayStation DualSense, Xbox Wireless Controller, arcade fight sticks) and keyboards on Linux.

---

## Arcade Cabinet Layout

The physical Sega *Fate/Grand Order Arcade* cabinet consists of:
- **8-Way Joystick**: Character movement
- **Button 1**: Primary Attack
- **Button 2**: Target Switch / Lock-On
- **Button 3**: Dash / Guard
- **Button 4**: Noble Phantasm (NP) activation
- **Capacitive Touch Screen**: Skill activation, Master Command Spells, and card draw selection
- **Aime RFID Reader**: Player login and card saving

---

## Recommended Gamepad Mapping

Modern controllers map naturally to the arcade layout:

| Cabinet Action | Xbox Controller | PlayStation DualSense | Arcade Stick | Keyboard Default |
| :--- | :--- | :--- | :--- | :--- |
| **Movement** | Left Analog / D-Pad | Left Analog / D-Pad | Joystick | `W` `A` `S` `D` |
| **Attack** | `X` Button | `Square` | Button 1 | `J` |
| **Target Lock** | `Y` Button | `Triangle` | Button 2 | `K` |
| **Dash / Evade** | `A` Button | `Cross` | Button 3 | `Space` / `L` |
| **Guard** | `B` Button | `Circle` | Button 4 | `I` |
| **Noble Phantasm**| Right Bumper (`RB`) | `R1` Button | Button 5 | `U` |
| **Camera Reset** | Left Bumper (`LB`) | `L1` Button | Button 6 | `O` |
| **Coin / Credit** | `Select` / `View` | `Share` / `Create` | Coin Switch | `5` |
| **Service Button**| `Start` / `Menu` | `Options` | Test Switch | `1` |
| **Touch Screen** | Left Mouse Click | Left Mouse Click | Touch Monitor | Left Click |

---

## In-Game Touch Screen on Linux

FGO Arcade makes extensive use of the cabinet's touch monitor for:
- Activating Servant Skills 1, 2, and 3
- Using Master Mystic Code skills & Command Spells
- Selecting Command Cards during the Chain phase

### How to Interact
1. **Mouse / Touchpad**: Click directly on the game window to touch that screen coordinate.
2. **Touchscreen Laptops / Monitors**: Touch inputs pass natively through Wayland/X11 to Wine.
3. **Cursor Visibility**: By default, `launch_linux.sh` preserves standard mouse input so you can easily see where you are clicking.

---

## Configuring Controls via Launcher

You can rebind all buttons visually without editing configuration files:
1. Open **FGO Launcher** (`./FGO_Launcher.sh`).
2. Navigate to the **Settings** tab on the left sidebar.
3. Select the **Controls** subtab.
4. Click any action row and press the key or button you wish to bind.
5. Click **Apply Changes** to save to `App/segatools.ini`.

---

## Advanced: Steam Input Integration

To use Steam's controller remapping, gyro, or custom deadzone features on Linux:

1. Open **Steam**.
2. Click **Games** > **Add a Non-Steam Game to My Library...**
3. Browse to `FGO_Launcher.sh` inside your FGO Arcade installation folder.
4. Right-click the shortcut in Steam > **Properties** > Enable **Steam Input**.
5. You can now configure DualSense haptics, Xbox elite paddles, or custom radial touch menus for servant skills!
