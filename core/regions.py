import pycountry
import pycountry_convert
from zoneinfo import available_timezones

# Initialize timezone cache
timezone_cache = sorted(available_timezones())

# Define regions
regions = {
    'Africa', 'America', 'Antarctica', 'Asia', 'Atlantic',
    'Australia', 'Europe', 'Indian', 'Pacific', 'Etc'
}

africa_regions = {
    'Northern Africa': ['Algeria', 'Egypt', 'Libya', 'Morocco', 'Sudan', 'Tunisia', 'Western Sahara'],
    'Western Africa': ['Benin', 'Burkina Faso', 'Cabo Verde', 'Côte d\'Ivoire', 'Gambia', 'Ghana', 'Guinea',
                       'Guinea-Bissau', 'Liberia', 'Mali', 'Mauritania', 'Niger', 'Nigeria', 'Senegal', 'Sierra Leone',
                       'Togo'],
    'Central Africa': ['Angola', 'Cameroon', 'Central African Republic', 'Chad', 'Congo',
                       'Democratic Republic of the Congo',
                       'Equatorial Guinea', 'Gabon', 'São Tomé and Príncipe'],
    'Eastern Africa': ['Burundi', 'Comoros', 'Djibouti', 'Eritrea', 'Ethiopia', 'Kenya', 'Madagascar', 'Malawi',
                       'Mauritius', 'Mozambique', 'Rwanda', 'Seychelles', 'Somalia', 'South Sudan', 'Tanzania',
                       'Uganda', 'Zambia', 'Zimbabwe'],
    'Southern Africa': ['Botswana', 'Eswatini', 'Lesotho', 'Namibia', 'South Africa'],
}

asia_regions = {
    'Western Asia': ['Armenia', 'Azerbaijan', 'Bahrain', 'Cyprus', 'Georgia', 'Iraq', 'Israel', 'Jordan', 'Kuwait',
                     'Lebanon', 'Oman', 'Qatar', 'Saudi Arabia', 'State of Palestine', 'Syria', 'Turkey',
                     'United Arab Emirates', 'Yemen'],
    'Central Asia': ['Kazakhstan', 'Kyrgyzstan', 'Tajikistan', 'Turkmenistan', 'Uzbekistan'],
    'South Asia': ['Afghanistan', 'Bangladesh', 'Bhutan', 'India', 'Iran', 'Maldives', 'Nepal', 'Pakistan',
                   'Sri Lanka'],
    'East Asia': ['China', 'Japan', 'Mongolia', 'North Korea', 'South Korea', 'Taiwan'],
    'Southeast Asia': ['Brunei', 'Cambodia', 'Indonesia', 'Laos', 'Malaysia', 'Myanmar', 'Philippines', 'Singapore',
                       'Thailand', 'Timor-Leste', 'Vietnam'],
}

europe_regions = {
    'Northern Europe': ['Denmark', 'Estonia', 'Finland', 'Iceland', 'Ireland', 'Latvia', 'Lithuania', 'Norway',
                        'Sweden', 'United Kingdom'],
    'Western Europe': ['Austria', 'Belgium', 'France', 'Germany', 'Liechtenstein', 'Luxembourg', 'Monaco',
                       'Netherlands', 'Switzerland'],
    'Eastern Europe': ['Belarus', 'Bulgaria', 'Czech Republic', 'Hungary', 'Moldova', 'Poland', 'Romania',
                       'Russia', 'Slovakia', 'Ukraine'],
    'Southern Europe': ['Albania', 'Andorra', 'Bosnia and Herzegovina', 'Croatia', 'Greece', 'Italy', 'Kosovo',
                        'North Macedonia', 'Malta', 'Montenegro', 'Portugal', 'San Marino', 'Serbia', 'Slovenia',
                        'Spain', 'Vatican City'],
}

north_america_regions = {
    'Northern America': ['Bermuda', 'Canada', 'Greenland', 'Mexico', 'United States'],
    'Central America': ['Belize', 'Costa Rica', 'El Salvador', 'Guatemala', 'Honduras', 'Nicaragua', 'Panama'],
    'Caribbean': ['Antigua and Barbuda', 'Bahamas', 'Barbados', 'Cuba', 'Dominica', 'Dominican Republic',
                  'Grenada', 'Haiti', 'Jamaica', 'Saint Kitts and Nevis', 'Saint Lucia',
                  'Saint Vincent and the Grenadines',
                  'Trinidad and Tobago', 'Puerto Rico']
}

us_regions = {
    'Northeast': ['Connecticut', 'Maine', 'Massachusetts', 'New Hampshire', 'Rhode Island', 'Vermont',
                  'New Jersey', 'New York', 'Pennsylvania'],
    'Midwest': ['Indiana', 'Illinois', 'Michigan', 'Ohio', 'Wisconsin',
                'Iowa', 'Kansas', 'Minnesota', 'Missouri', 'Nebraska', 'North Dakota', 'South Dakota'],
    'South': ['Delaware', 'Florida', 'Georgia', 'Maryland', 'North Carolina', 'South Carolina', 'Virginia',
              'District of Columbia', 'West Virginia', 'Alabama', 'Kentucky', 'Mississippi', 'Tennessee',
              'Arkansas', 'Louisiana', 'Oklahoma', 'Texas'],
    'West': ['Arizona', 'Colorado', 'Idaho', 'Montana', 'Nevada', 'New Mexico', 'Utah', 'Wyoming',
             'Alaska', 'California', 'Hawaii', 'Oregon', 'Washington'],
}

us_state_timezones = {
    'Alabama': ['Central Time'],
    'Alaska': ['Alaska Time'],
    'Arizona': ['Mountain Time'],
    'Arkansas': ['Central Time'],
    'California': ['Pacific Time'],
    'Colorado': ['Mountain Time'],
    'Connecticut': ['Eastern Time'],
    'Delaware': ['Eastern Time'],
    'Florida': ['Eastern Time', 'Central Time'],
    'Georgia': ['Eastern Time'],
    'Hawaii': ['Hawaii Time'],
    'Idaho': ['Mountain Time', 'Pacific Time'],
    'Illinois': ['Central Time'],
    'Indiana': ['Eastern Time', 'Central Time'],
    'Iowa': ['Central Time'],
    'Kansas': ['Central Time', 'Mountain Time'],
    'Kentucky': ['Eastern Time', 'Central Time'],
    'Louisiana': ['Central Time'],
    'Maine': ['Eastern Time'],
    'Maryland': ['Eastern Time'],
    'Massachusetts': ['Eastern Time'],
    'Michigan': ['Eastern Time', 'Central Time'],
    'Minnesota': ['Central Time'],
    'Mississippi': ['Central Time'],
    'Missouri': ['Central Time'],
    'Montana': ['Mountain Time'],
    'Nebraska': ['Central Time', 'Mountain Time'],
    'Nevada': ['Pacific Time', 'Mountain Time'],
    'New Hampshire': ['Eastern Time'],
    'New Jersey': ['Eastern Time'],
    'New Mexico': ['Mountain Time'],
    'New York': ['Eastern Time'],
    'North Carolina': ['Eastern Time'],
    'North Dakota': ['Central Time', 'Mountain Time'],
    'Ohio': ['US/Eastern'],
    'Oklahoma': ['Central Time'],
    'Oregon': ['Pacific Time', 'Mountain Time'],
    'Pennsylvania': ['Eastern Time'],
    'Rhode Island': ['Eastern Time'],
    'South Carolina': ['Eastern Time'],
    'South Dakota': ['Central Time', 'Mountain Time'],
    'Tennessee': ['Central Time', 'Eastern Time'],
    'Texas': ['Central Time', 'Mountain Time'],
    'Utah': ['Mountain Time'],
    'Vermont': ['US/Eastern'],
    'Virginia': ['Eastern Time'],
    'Washington': ['Pacific Time'],
    'West Virginia': ['Eastern Time'],
    'Wisconsin': ['Central Time'],
    'Wyoming': ['Mountain Time'],
    'District of Columbia': ['Eastern Time'],
}

continent_regions = {
    'Africa': africa_regions,
    'Asia': asia_regions,
    'Europe': europe_regions,
    'North America': north_america_regions,
}

region_timezones = {region: [tz for tz in timezone_cache if tz.startswith(f"{region}/")] for region in regions}

continent_to_countries = {}

for country in pycountry.countries:
    country_code = country.alpha_2
    country_name = country.name
    try:
        continent_code = pycountry_convert.country_alpha2_to_continent_code(country_code)
        continent_name = pycountry_convert.convert_continent_code_to_continent_name(continent_code)
    except KeyError:
        continue

    if continent_name == 'Americas':
        if country_name in north_america_regions['Northern America'] + \
                north_america_regions['Central America'] + \
                north_america_regions['Caribbean']:
            continent_name = 'North America'
        else:
            continent_name = 'South America'
    
    if continent_name not in continent_to_countries:
        continent_to_countries[continent_name] = []

    continent_to_countries[continent_name].append({'code': country_code, 'name': country_name})
