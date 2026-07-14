/* ===================================================================
   Current Location Button
   =================================================================== */

function getCurrentLocation() {

    if (!navigator.geolocation) {
        alert("Geolocation is not supported by your browser.");
        return;
    }

    const btn = document.getElementById("location-btn");
    const originalText = btn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = "📍 Getting Location...";

    navigator.geolocation.getCurrentPosition(

        function(position) {

            const lat = position.coords.latitude;
            const lng = position.coords.longitude;

            document.getElementById("lat-input").value = lat.toFixed(6);
            document.getElementById("lng-input").value = lng.toFixed(6);

            placeMarker(lat, lng);
            map.setView([lat, lng], 15);

            btn.disabled = false;
            btn.innerHTML = originalText;

        },

        function(error) {

            btn.disabled = false;
            btn.innerHTML = originalText;

            switch(error.code){

                case error.PERMISSION_DENIED:
                    alert("Location permission denied.");
                    break;

                case error.POSITION_UNAVAILABLE:
                    alert("Location unavailable.");
                    break;

                case error.TIMEOUT:
                    alert("Location request timed out.");
                    break;

                default:
                    alert("Unable to get current location.");
            }

            console.error(error);

        },

        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }

    );
}

// Attach click event
document.getElementById("location-btn").addEventListener("click", getCurrentLocation);
