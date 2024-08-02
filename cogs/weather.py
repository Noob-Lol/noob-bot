import json, requests
from discord.ext import commands

def get_quote(city):
        url = "https://weatherapi-com.p.rapidapi.com/forecast.json"
        querystring = {"q":city,"days":"3"}
        headers = {
             # this is not my api key
            "X-RapidAPI-Key": "f77c5bde9bmsh775458a2f3f1651p175e25jsn8b6a2f52c501",
            "X-RapidAPI-Host": "weatherapi-com.p.rapidapi.com"
        }
        response = requests.get(url, headers=headers, params=querystring)
        json_data = json.loads(response.text)
        return json_data

class WeatherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="weather", help="Enter the name of the city")
    async def weather(self,ctx, city: str):
        weather = get_quote(city)
        name = weather['location']['name']
        region = weather['location']['region']
        country = weather['location']['country']
        local_time = weather['location']['localtime']
        temp = weather['current']['temp_c']
        cond = weather['current']['condition']['text']
        wind_kph = weather['current']['wind_kph']
        feelslike_c = weather['current']['feelslike_c']
        date1 = weather['forecast']['forecastday'][0]['date']
        forecast1_maxtemp = weather['forecast']['forecastday'][0]['day']['maxtemp_c']
        forecast1_mintemp = weather['forecast']['forecastday'][0]['day']['mintemp_c']
        forecast1_rainchance = weather['forecast']['forecastday'][0]['day']['daily_chance_of_rain']
        date2 = weather['forecast']['forecastday'][1]['date']
        forecast2_maxtemp = weather['forecast']['forecastday'][1]['day']['maxtemp_c']
        forecast2_mintemp = weather['forecast']['forecastday'][1]['day']['mintemp_c']
        forecast2_rainchance = weather['forecast']['forecastday'][1]['day']['daily_chance_of_rain']
        date3 = weather['forecast']['forecastday'][2]['date']
        forecast3_maxtemp = weather['forecast']['forecastday'][2]['day']['maxtemp_c']
        forecast3_mintemp = weather['forecast']['forecastday'][2]['day']['mintemp_c']
        forecast3_rainchance = weather['forecast']['forecastday'][2]['day']['daily_chance_of_rain']
        await ctx.channel.send("City: "+name+"\nRegion: " + region +     "\nCountry: " + country + "\nLocal Time: " + str(local_time) + "\nTemperature: " + str(temp)+"℃" + "\nCondition: "+ cond + "\nWind speed: "+str(wind_kph)+" kph"+"\nFeels like "+str(feelslike_c)+"℃"+"\nForecast:"+"\n"+str(date1)+": "+str(forecast1_maxtemp)+" ~ "+str(forecast1_mintemp)+", "+"Rain Chance: "+str(forecast1_rainchance)+"\n"+date2+": "+str(forecast2_maxtemp)+" ~ "+str(forecast2_mintemp)+", "+"Rain Chance: "+str(forecast2_rainchance)+"\n"+str(date3)+": "+str(forecast3_maxtemp)+" ~ "+str(forecast3_mintemp)+", "+"Rain Chance: "+str(forecast3_rainchance))

async def setup(bot):
    await bot.add_cog(WeatherCog(bot))