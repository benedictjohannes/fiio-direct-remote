k17_ctrl() {
    local action=$1
    local value=$2

    # Dynamic target resolution via mDNS or MAC prefix
    local k17_ip=$(avahi-resolve -n ingenic.local 2>/dev/null | awk '{print $2}')
    if [[ -z "$k17_ip" ]]; then
        k17_ip=$(ip n | awk '/40:d9:5a/ {print $1; exit}')
    fi

    if [[ -z "$k17_ip" ]]; then
        echo "Error: K17 DAC not found on local network."
        return 1
    fi

    case "$action" in
        status)
            local raw_resp
            raw_resp=$( (echo -n "05010008"; sleep 0.3) | timeout 1 nc "$k17_ip" 12100 2>/dev/null | sed -n 's/^[^{]*\({.*}\)[^}]*$/\1/p')

            if [[ -z "$raw_resp" ]]; then
                echo "Error: Could not retrieve status frame from K17 ($k17_ip)."
                return 1
            fi

            if command -v jq >/dev/null 2>&1; then
                echo "$raw_resp" | jq .
            else
                echo "$raw_resp"
            fi
            ;;

        vol)
            # GETTER: If no volume argument is passed, fetch and display current volume
            if [[ -z "$value" ]]; then
                local raw_resp
                raw_resp=$( (echo -n "05010008"; sleep 0.3) | timeout 1 nc "$k17_ip" 12100 2>/dev/null | sed -n 's/^[^{]*\({.*}\)[^}]*$/\1/p')
                
                if [[ -z "$raw_resp" ]]; then
                    echo "Error: Could not retrieve volume from K17 ($k17_ip)."
                    return 1
                fi

                if command -v jq >/dev/null 2>&1; then
                    echo "$raw_resp" | jq -r '.currentVolume'
                else
                    echo "$raw_resp" | sed -n 's/.*"currentVolume":\([0-9]*\).*/\1/p'
                fi
                return 0
            fi

            # SETTER: Validate bounds (0 to 100)
            if [[ "$value" -lt 0 || "$value" -gt 100 ]]; then
                echo "Usage: k17_ctrl vol [0-100]"
                return 1
            fi

            local hex_val=$(printf "%04X" "$value")
            echo -n "0502000c${hex_val}" > /dev/tcp/"$k17_ip"/12100
            echo "K17 ($k17_ip) Volume set to $value"
            ;;

        mode)
            case "$value" in
                usb)       echo -n "0657000c0001" > /dev/tcp/"$k17_ip"/12100 ;;
                opt)       echo -n "0657000c0002" > /dev/tcp/"$k17_ip"/12100 ;;
                coax)      echo -n "0657000c0003" > /dev/tcp/"$k17_ip"/12100 ;;
                line)      echo -n "0657000c0004" > /dev/tcp/"$k17_ip"/12100 ;;
                bal|xlr)   echo -n "0657000c0005" > /dev/tcp/"$k17_ip"/12100 ;;
                bt)        echo -n "0657000c0006" > /dev/tcp/"$k17_ip"/12100 ;;
                stream)    echo -n "0657000c0007" > /dev/tcp/"$k17_ip"/12100 ;;
                *)         echo "Usage: k17_ctrl mode <usb|opt|coax|line|bal|bt|stream>"; return 1 ;;
            esac
            echo "K17 ($k17_ip) Input mode switched to $value"
            ;;

        *)
            echo "Usage: k17_ctrl <status|vol|mode> [value]"
            return 1
            ;;
    esac
}